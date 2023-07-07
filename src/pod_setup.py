"""Classes for POD setup routines previously located in data_manager.DataSourceBase
"""
from abc import ABC
import logging
import os
import io
from pathlib import Path
from typing import Type

from src import cli, util, data_sources
import intake_esm
import dataclasses as dc

_log = logging.getLogger(__name__)


class PodBaseClass(metaclass=util.MDTFABCMeta):
    """Base class for POD setup methods
    """
    def parse_pod_settings_file(self, code_root: str):
        pass

    def setup_pod(self, config: util.NameSpace):
        pass

    def setup_var(self, pod, v):
        pass


class PodObject(util.PODLoggerMixin, util.MDTFObjectBase, PodBaseClass, ABC):
    """Class to hold pod information"""
    # name: str  Class atts inherited from MDTFObjectBase
    # _id
    # _parent: object
    # status: ObjectStatus
    pod_dims = dict()
    pod_data = dict()
    pod_vars = dict()
    pod_settings = dict()
    cases = dict()

    MODEL_DATA_DIR = dict()
    MODEL_WORK_DIR = dict()
    MODEL_OUT_DIR = dict()

    overwrite: bool = False
    # explict 'program' attribute in settings
    _interpreters = {'.py': 'python', '.ncl': 'ncl', '.R': 'Rscript'}
    runtime_requirements: dict = dc.field(default_factory=dict)
    driver: str = ""
    program: str = ""
    pod_env_vars: util.ConsistentDict = dc.field(default_factory=util.ConsistentDict)
    log_file: io.IOBase = dc.field(default=None, init=False)
    nc_largefile: bool = False
    log_file: io.IOBase = dc.field(default=None, init=False)

    def __init__(self, name: str, runtime_config: util.NameSpace):
        self.name = name
        self.init_log()
        # define global environment variables: those that apply to the entire POD
        self.pod_env_vars = os.environ.copy()
        self.pod_env_vars['RGB'] = os.path.join(runtime_config.code_root, 'shared', 'rgb')
        # globally enforce non-interactive matplotlib backend
        # see https://matplotlib.org/3.2.2/tutorials/introductory/usage.html#what-is-a-backend
        self.pod_env_vars['MPLBACKEND'] = "Agg"
        self.nc_largefile = runtime_config.large_file
        # set up work/output directories
        self.paths = util.PathManager(runtime_config, self.global_env_vars)
        self.paths.set_pod_paths(self.name, runtime_config, self.global_env_vars)

    @property
    def _log_name(self):
        # POD loggers sit in a subtree of the DataSource logger distinct from
        # the DataKey loggers; the two subtrees are distinguished by class name
        _log_name = f"{self.name}_{self._id}".replace('.', '_')
        return f"{self._parent._log_name}.{self.__class__.__name__}.{_log_name}"

    def close_log_file(self, log=True):
        if self.log_file is not None:
            if log:
                self.log_file.write(self.format_log(children=False))
            self.log_file.close()

    def iter_case_names(self):
        """Iterator returning :c
        """
        yield self.cases.keys()

    def parse_pod_settings_file(self, code_root: str) -> util.NameSpace:
        """Parse the POD settings file"""
        settings_file_query = Path(code_root, 'diagnostics', self.name).glob('*settings.*')
        settings_file_path = str([p for p in settings_file_query][0])
        # Use wildcard to support settings file in yaml and jsonc format
        settings_dict = cli.parse_config_file(settings_file_path)
        return util.NameSpace.fromDict({k: settings_dict[k] for k in settings_dict.keys()})

    def verify_pod_settings(self):
        """Verify that the POD settings file has the required entries"""
        required_settings = {"driver": str, "long_name": "", "convention": "",
                             "runtime_requirements": list}
        value = []
        try:
            value = [i for i in required_settings if i in self.pod_settings
                     and isinstance(self.pod_settings[i], type(required_settings[i]))]
        except Exception as exc:
            raise util.PodConfigError("Caught Exception: required setting %s not in pod setting file %s", value[0])\
                from exc

    def _get_pod_settings(self, pod_settings_dict: util.NameSpace):
        self.pod_settings = util.NameSpace.toDict(pod_settings_dict.settings)

    def _get_pod_data(self, pod_settings_dict: util.NameSpace):
        self.pod_data = util.NameSpace.toDict(pod_settings_dict.data)

    def _get_pod_dims(self, pod_settings_dict: util.NameSpace):
        self.pod_dims = util.NameSpace.toDict(pod_settings_dict.dims)

    def _get_pod_vars(self, pod_settings_dict: util.NameSpace):
        self.pod_vars = util.NameSpace.toDict(pod_settings_dict.varlist)

    def get_pod_data_subset(self, catalog_path: str, case_data_source):
        cat = intake.open_esm_datastore(catalog_path)
        # filter catalog by desired variable and output frequency
        tas_subset = cat.search(variable_id=case_data_source.varlist.iter_vars(),
                                frequency=self.pod_data['freq'])

    def query_files_in_time_range(self, startdate, enddate):
        pass

    def append_pod_env_vars(self, pod_input):
        self.global_env_vars.update(v for v in pod_input.pod_env_vars)

    def set_entry_point(self):
        """Locate the top-level driver script for the POD.

        Raises: :class:`~util.PodRuntimeError` if driver script can't be found.
        """
        self.driver = os.path.join(self.paths.POD_CODE_DIR, self.pod_settings["driver"])
        if not self.driver:
            raise util.PodRuntimeError((f"No driver script found in "
                                        f"{self.paths.POD_CODE_DIR}. Specify 'driver' in settings.jsonc."),
                                       self)
        if not os.path.isabs(self.driver):  # expand relative path
            self.driver = os.path.join(self.paths.POD_CODE_DIR, self.driver)

        self.log.debug("Setting driver script for %s to '%s'.",
                       self.full_name, self.driver)

    def set_interpreter(self):
        """Determine what executable should be used to run the driver script.

        .. note::
           Existence of the program on the environment's ``$PATH`` isn't checked
           until before the POD runs (see :mod:`src.environment_manager`.)
        """

        if not self.program:
            # Find ending of filename to determine the program that should be used
            _, driver_ext = os.path.splitext(self.driver)
            # Possible error: Driver file type unrecognized
            if driver_ext not in self._interpreters:
                raise util.PodRuntimeError((f"Don't know how to call a '{driver_ext}' "
                                            f"file.\nSupported programs: {list(self._interpreters.values())}"),
                                           self
                                           )
            self.program = self._interpreters[driver_ext]
            self.log.debug("Set program for %s to '%s'.",
                           self.full_name, self.program)

    def setup_pod(self, runtime_config: util.NameSpace,):
        """Update POD information
        """
        # Parse the POD settings file
        pod_input = self.parse_pod_settings_file(runtime_config.code_root)
        self._get_pod_settings(pod_input)
        self._get_pod_vars(pod_input)
        self._get_pod_data(pod_input)
        self._get_pod_dims(pod_input)
        self.verify_pod_settings()
        self.set_interpreter()
        # run the PODs on data that has already been preprocessed
        # PODs will ingest input directly from catalog that (should) contain
        # the information for the saved preprocessed files, and a pre-existing case_env file
        if runtime_config.persist_data:
            pass
        elif runtime_config.run_pp:
            for case_name, case_dict in runtime_config.case_list.items():
                # instantiate the data_source class instance for the specified convention
                self.cases[case_name] = data_sources.data_source[case_dict.convention.upper() +
                                                                 "DataSource"](case_dict, parent=self)

                #util.NameSpace.fromDict({k: case_dict[k] for k in case_dict.keys()})
                if self.pod_settings['convention'].lower() != case_dict.convention.lower():
                    # translate variable(s) to user_specified standard if necessary

                    #self.cases[case_name].varlist = varlist_util.Varlist.from_struct(self)
                    self.cases[case_name].get_varlist(self)
                else:
                    pass


            # get level

        else:
            pass
        # run custom scripts on dataset
        if any([s for s in runtime_config.my_scripts]):
            pass

        # ref for dict comparison
        # https://stackoverflow.com/questions/20578798/python-find-matching-values-in-nested-dictionary

        #cat_subset = self.get_pod_data_subset(runtime_config.CATALOG_PATH, runtime_config.case_list)

        #self.setup_var(v, case_dict.attrs.date_range, case_name)

        # preprocessor will edit case varlist alternates, depending on enabled functions
        # self is the Mul
        #self.preprocessor = self._PreprocessorClass(self)
        # self=MulirunDiagnostic instance, and is passed as data_mgr parm to access
        # cases
        #self.preprocessor.edit_request(self)

        for case_name in self.cases.keys():
            for v in case_name.iter_children():
                # deactivate failed variables, now that alternates are fully
                # specified
                if v.last_exception is not None and not v.failed:
                    v.deactivate(v.last_exception, level=logging.WARNING)
            if case_name.status == util.ObjectStatus.NOTSET and \
                    any(v.status == util.ObjectStatus.ACTIVE for v in case_name.iter_children()):
                case_name.status = util.ObjectStatus.ACTIVE
        # set MultirunDiagnostic object status to Active if all case statuses are Active
        if self.status == util.ObjectStatus.NOTSET and \
                all(case.status == util.ObjectStatus.ACTIVE for case in self.cases):
            self.status = util.ObjectStatus.ACTIVE


