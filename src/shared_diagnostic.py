from __future__ import absolute_import, division, print_function, unicode_literals
import os
from src import six
import glob
import shutil
from src import util
from src import util_mdtf


@six.python_2_unicode_compatible
class PodRequirementFailure(Exception):
    """Exception raised if POD doesn't have required resoruces to run. 
    """
    def __init__(self, pod, msg=None):
        self.pod = pod
        self.msg = msg

    def __str__(self):
        if self.msg is not None:
            return ("Requirements not met for {0}."
                "\nReason: {1}.").format(self.pod.name, self.msg)
        else:
            return 'Requirements not met for {}.'.format(self.pod.name)

class Diagnostic(object):
    """Class holding configuration for a diagnostic script.

    This is the analogue of TestCase in the xUnit analogy.

    Object attributes are read from entries in the settings section of the POD's
    settings.json file upon initialization.

    Attributes:
        driver (:py:obj:`str`): Filename of the top-level driver script for the POD.
        long_name (:py:obj:`str`): POD's name used for display purposes. May contain spaces.
        description (:py:obj:`str`): Short description of POD inserted by the link in the
            top-level index.html file.
        required_programs (:py:obj:`list` of :py:obj:`str`, optional): List of 
            executables required by the POD (typically language interpreters). 
            validate_environment.sh will make sure these are on the environment's
            $PATH before the POD is run.
        required_ncl_scripts (:py:obj:`list` of :py:obj:`str`, optional): List of NCL 
            scripts required by the POD, if any.  
            validate_environment.sh will make sure these are on the environment's
            $PATH before the POD is run.
    """

    def __init__(self, pod_name, verbose=0):
        """POD initializer. Given a POD name, we attempt to read a settings.json 
        file in a subdirectory of ``/diagnostics`` by that name and parse the
        contents.

        Args:
            pod_name (:py:obj:`str`): Name of the POD to initialize.
            verbose (:py:obj:`int`, optional): Logging verbosity level. Default 0.
        """
        config = util_mdtf.ConfigManager()
        assert pod_name in config.pods
        # define attributes manually so linter doesn't complain
        # others are set in _parse_pod_settings
        self.driver = ""
        self.program = ""
        self.pod_env_vars = dict()
        self.skipped = None
        self.POD_CODE_DIR = ""
        self.POD_OBS_DATA = ""
        self.POD_WK_DIR = ""
        self.POD_OUT_DIR = ""
        self.TEMP_HTML = ""

        self.name = pod_name
        self.code_root = config.paths.CODE_ROOT
        self.dry_run = config.config.get('dry_run', False)
        d = config.pods[pod_name]
        self.__dict__.update(self._parse_pod_settings(d['settings']))
        self.varlist = self._parse_pod_varlist(d['varlist'])

    def iter_vars_and_alts(self):
        """Generator iterating over all variables and alternates in POD's varlist.
        """
        for var in self.varlist:
            yield var
            for alt_var in var.alternates:
                yield alt_var

    def _parse_pod_settings(self, settings, verbose=0):
        """Private method called by :meth:`~shared_diagnostic.Diagnostic.__init__`.

        Args:
            settings (:py:obj:`dict`): Contents of the settings portion of the POD's
                settings.json file.
            verbose (:py:obj:`int`, optional): Logging verbosity level. Default 0.

        Returns:
            Dict of parsed settings.
        """
        d = {}
        d['pod_name'] = self.name # redundant
        # define empty defaults to avoid having to test existence of attrs
        for str_attr in ['long_name', 'description', 'env', 'convention']:
            d[str_attr] = ''
        for list_attr in ['varlist']:
            d[list_attr] = []
        for dict_attr in ['runtime_requirements']:
            d[dict_attr] = dict()
        for obj_attr in ['process_obj', 'logfile_obj']:
            d[obj_attr] = None

        # overwrite with contents of settings.json file
        d.update(settings)

        if 'variable_convention' in d:
            d['convention'] = d['variable_convention']
            del d['variable_convention']
        elif not d.get('convention', None):
            d['convention'] = 'CF'
        for key, val in iter(d['runtime_requirements'].items()):
            d['runtime_requirements'][key] = util.coerce_to_iter(val)
        if (verbose > 0): 
            print(self.name + " settings: ")
            print(d)
        return d

    def _parse_pod_varlist(self, varlist, verbose=0):
        """Private method called by :meth:`~shared_diagnostic.Diagnostic.__init__`.

        Args:
            varlist (:py:obj:`list` of :py:obj:`dict`): Contents of the varlist portion 
                of the POD's settings.json file.
            verbose (:py:obj:`int`, optional): Logging verbosity level. Default 0.

        Returns:
            varlist
        """
        default_file_required = True 
        for i, var in enumerate(varlist):
            assert var['freq'] in ['1hr', '3hr', '6hr', 'day', 'mon'], \
                "WARNING: didn't find "+var['freq']+" in frequency options "+\
                    " (set in "+__file__+": parse_pod_varlist)"
            if 'requirement' in var:
                varlist[i]['required'] = (var['requirement'].lower() == 'required')
            elif 'required' not in varlist[i]:
                varlist[i]['required'] = default_file_required
            if 'alternates' not in var:
                varlist[i]['alternates'] = []
            else:
                varlist[i]['alternates'] = util.coerce_to_iter(var['alternates'])
        if (verbose > 0): 
            print(self.name + " varlist: ")
            print(varlist)
        return varlist

    # -------------------------------------

    def setUp(self, verbose=0):
        """Perform filesystem operations and checks prior to running the POD. 

        In order, this 1) sets environment variables specific to the POD, 2)
        creates POD-specific working directories, and 3) checks for the existence
        of the POD's driver script.

        Note:
            The existence of data files is checked with 
            :meth:`data_manager.DataManager.fetchData`
            and the runtime environment is validated separately as a function of
            :meth:`environment_manager.EnvironmentManager.run`. This is because 
            each POD is run in a subprocess (due to the necessity of supporting
            multiple languages) so the validation must take place in that 
            subprocess.

        Raises: :exc:`~shared_diagnostic.PodRequirementFailure` if requirements
            aren't met. This is re-raised from the 
            :meth:`~shared_diagnostic.Diagnostic._check_pod_driver` and
            :meth:`~shared_diagnostic.Diagnostic._check_for_varlist_files` 
            subroutines.
        """
        self._set_pod_env_vars(verbose)
        self._setup_pod_directories()
        if isinstance(self.skipped, Exception):
            # already encountered reason we can't run this, re-raise it here 
            # to log it
            raise PodRequirementFailure(self,
                "Caught {} exception:\n{}".format(
                    type(self.skipped).__name__, self.skipped
                ))
        try:
            self._check_pod_driver(verbose)
            (found_files, missing_files) = self._check_for_varlist_files(
                self.varlist, verbose
            )
            self.found_files = found_files
            self.missing_files = missing_files
            if missing_files:
                raise PodRequirementFailure(self,
                    "Couldn't find required model data files:\n{}".format(
                        "\n".join(missing_files)
                    ))
            else:
                if (verbose > 0): print("No known missing required input files")
        except PodRequirementFailure as exc:
            print(exc)
            raise exc

    def _set_pod_env_vars(self, verbose=0):
        """Private method called by :meth:`~shared_diagnostic.Diagnostic.setUp`.
        Sets all environment variables for POD.

        Args:
            verbose (:py:obj:`int`, optional): Logging verbosity level. Default 0.
        """
        self.pod_env_vars.update({
            "POD_HOME": self.POD_CODE_DIR, # location of POD's code
            "OBS_DATA": self.POD_OBS_DATA, # POD's observational data
            "WK_DIR": self.POD_WK_DIR,     # POD's subdir within working directory
        })
        # Set env vars POD has inherited globally and from current case 
        # (set in DataManager._setup_pod).
        for key, val in iter(self.pod_env_vars.items()):
            util_mdtf.setenv(key, val, self.pod_env_vars, verbose=verbose, overwrite=True) 

        # Set env vars for variable and axis names:
        axes = dict()
        ax_status = dict()
        for var in self.iter_vars_and_alts():
            # util_mdtf.setenv(var.original_name, var.name_in_model, 
            #     self.pod_env_vars, verbose=verbose)
            # make sure axes found for different vars are consistent
            for ax_name, ax_attrs in iter(var.axes.items()):
                if 'MDTF_envvar' not in ax_attrs:
                    print(("\tWarning: don't know env var to set" 
                        "for axis name {}").format(ax_name))
                    envvar_name = ax_name+'_coord'
                else:
                    envvar_name = ax_attrs['MDTF_envvar']
                set_from_axis = ax_attrs.get('MDTF_set_from_axis', None)
                if envvar_name not in axes:
                    # populate dict
                    axes[envvar_name] = ax_name
                    ax_status[envvar_name] = set_from_axis
                elif axes[envvar_name] != ax_name and ax_status[envvar_name] is None:
                    # populated with defaults, but now overwrite with name that
                    # was confirmed from file
                    axes[envvar_name] = ax_name
                    ax_status[envvar_name] = set_from_axis
                elif axes[envvar_name] != ax_name \
                    and ax_status[envvar_name] == set_from_axis:
                    # names found in two different files disagree - raise error
                    raise PodRequirementFailure(self,
                        ("Two variables have conflicting axis names {}:"
                            "({}!={})").format(
                                envvar_name, axes[envvar_name], ax_name
                    ))
        for key, val in iter(axes.items()): 
            util_mdtf.setenv(key, val, self.pod_env_vars, verbose=verbose)

    def _setup_pod_directories(self, verbose =0):
        """Private method called by :meth:`~shared_diagnostic.Diagnostic.setUp`.

        Args:
            verbose (:py:obj:`int`, optional): Logging verbosity level. Default 0.
        """
        util_mdtf.check_required_dirs(
            already_exist =[self.POD_CODE_DIR, self.POD_OBS_DATA], 
            create_if_nec = [self.POD_WK_DIR], 
            verbose=verbose)
        dirs = ['', 'model', 'model/PS', 'model/netCDF', 
            'obs', 'obs/PS','obs/netCDF']
        for d in dirs:
            if not os.path.exists(os.path.join(self.POD_WK_DIR, d)):
                os.makedirs(os.path.join(self.POD_WK_DIR, d))

    def _check_pod_driver(self, verbose=0):
        """Private method called by :meth:`~shared_diagnostic.Diagnostic.setUp`.

        Args:
            verbose (:py:obj:`int`, optional): Logging verbosity level. Default 0.

        Raises: :exc:`~shared_diagnostic.PodRequirementFailure` if driver script
            can't be found.
        """
        func_name = "check_pod_driver "
        if (verbose > 1): 
            print(func_name," received POD settings: ", self.__dict__)
        programs = util_mdtf.get_available_programs()

        if self.driver == '':  
            print("WARNING: no valid driver entry found for ", self.name)
            #try to find one anyway
            try_filenames = [self.name+".", "driver."]      
            file_combos = [ file_root + ext for file_root \
                in try_filenames for ext in programs]
            if verbose > 1: 
                print("Checking for possible driver names in {} {}".format(
                    self.POD_CODE_DIR, file_combos
                ))
            for try_file in file_combos:
                try_path = os.path.join(self.POD_CODE_DIR, try_file)
                if verbose > 1: print(" looking for driver file "+try_path)
                if os.path.exists(try_path):
                    self.driver = try_path
                    if (verbose > 0): 
                        print("Found driver script for {}: {}".format(
                            self.name, self.driver
                        ))
                    break    #go with the first one found
                else:
                    if (verbose > 1 ): print("\t "+try_path+" not found...")
        if self.driver == '':
            raise PodRequirementFailure(self, 
                """No driver script found in {}. Specify 'driver' in 
                settings.jsonc.""".format(self.POD_CODE_DIR)
                )

        if not os.path.isabs(self.driver): # expand relative path
            self.driver = os.path.join(self.POD_CODE_DIR, self.driver)
        if not os.path.exists(self.driver):
            raise PodRequirementFailure(self, 
                "Unable to locate driver script {}.".format(self.driver)
                )

        if self.program == '':
            # Find ending of filename to determine the program that should be used
            driver_ext  = self.driver.split('.')[-1]
            # Possible error: Driver file type unrecognized
            if driver_ext not in programs:
                raise PodRequirementFailure(self, 
                    ("{} doesn't know how to call a .{} file.\n"
                    "Supported programs: {}").format(
                        func_name, driver_ext, programs
                ))
            self.program = programs[driver_ext]
            if ( verbose > 1): 
                print(func_name +": Found program "+programs[driver_ext])

    def _check_for_varlist_files(self, varlist, verbose=0):
        """Verify that all data files needed by a POD exist locally.
        
        Private method called by :meth:`~data_manager.DataManager.fetchData`.

        Args:
            varlist (:py:obj:`list` of :py:obj:`dict`): Contents of the varlist portion 
                of the POD's settings.json file.
            verbose (:py:obj:`int`, optional): Logging verbosity level. Default 0.

        Returns: :py:obj:`tuple` of found and missing file lists. Note that this is called
            recursively.
        """
        func_name = "\t \t check_for_varlist_files :"
        if ( verbose > 2 ): 
            print(func_name+" check_for_varlist_files called with ", varlist)
        found_list = []
        missing_list = []
        if self.dry_run:
            print('DRY_RUN: Skipping POD file check')
            return (found_list, missing_list)
        for ds in varlist:
            if (verbose > 2 ): print(func_name +" "+ds.name)
            filepath = ds._local_data
            if os.path.isfile(filepath):
                found_list.append(filepath)
                continue
            if (not ds.required):
                print("WARNING: optional file not found ", filepath)
                continue
            if not ds.alternates:
                print(("ERROR: missing required file {}. "
                    "No alternatives found").format(filepath))
                missing_list.append(filepath)
            else:
                alt_list = ds.alternates
                print(("WARNING: required file not found: {}."
                    "\n\tLooking for alternatives: ").format(filepath))
                for alt_var in alt_list: 
                    # maybe some way to do this w/o loop since check_ takes a list
                    if (verbose > 1): 
                        print("\t\t examining alternative ",alt_var)
                    (new_found, new_missing) = self._check_for_varlist_files(
                        [alt_var], verbose=verbose
                    )
                    found_list.extend(new_found)
                    missing_list.extend(new_missing)
        # remove empty list entries
        found_list = [x for x in found_list if x is not None]
        missing_list = [x for x in missing_list if x is not None]
        # nb, need to return due to recursive call
        if (verbose > 2): 
            print("check_for_varlist_files returning ", missing_list)
        return (found_list, missing_list)

    # -------------------------------------

    def run_commands(self):
        """Produces the shell command(s) to run the POD. Called by 
        :meth:`environment_manager.EnvironmentManager.run`.

        Returns:
            (:py:obj:`list` of :py:obj:`str`): Command-line invocation to run the POD.
        """
        #return [self.program + ' ' + self.driver]
        return ['/usr/bin/env python -u '+self.driver]

    def validate_commands(self):
        """Produces the shell command(s) to validate the POD's runtime environment 
        (ie, check for all requested third-party module dependencies.)

        Called by :meth:`environment_manager.EnvironmentManager.run`. 
        Dependencies are passed as arguments to the shell script 
        ``src/validate_environment.sh``, which is invoked in the POD's subprocess
        before the POD is run.

        Returns:
            (:py:obj:`list` of :py:obj:`str`): Command-line invocation to validate 
                the POD's runtime environment.
        """
        # pylint: disable=maybe-no-member
        command_path = os.path.join(self.code_root, 'src', 'validate_environment.sh')
        command = [
            command_path,
            ' -v',
            ' -p '.join([''] + list(self.runtime_requirements)),
            ' -z '.join([''] + list(self.pod_env_vars)),
            ' -a '.join([''] + self.runtime_requirements.get('python', [])),
            ' -b '.join([''] + self.runtime_requirements.get('ncl', [])),
            ' -c '.join([''] + self.runtime_requirements.get('Rscript', []))
        ]
        return [''.join(command)]

    # -------------------------------------

    def tearDown(self, verbose=0):
        """Performs cleanup tasks when the POD has finished running.

        In order, this 1) creates the POD's HTML output page from its included
        template, replacing ``CASENAME`` and other template variables with their
        current values, and adds a link to the POD's page from the top-level HTML
        report; 2) converts the POD's output plots (in PS or EPS vector format) 
        to a bitmap format for webpage display; 3) Copies all requested files to
        the output directory and deletes temporary files.

        Args:
            verbose (:py:obj:`int`, optional): Logging verbosity level. Default 0.
        """
        # add link and description to main html page
        self.append_result_link(self.skipped)

        if not isinstance(self.skipped, Exception):
            self.make_pod_html()
            self.convert_pod_figures('model')
            self.convert_pod_figures('obs')
            self.cleanup_pod_files()

        if verbose > 0: 
            print("---  MDTF.py Finished POD "+self.name+"\n")
            # elapsed = timeit.default_timer() - start_time
            # print(pod+" Elapsed time ",elapsed)

    def make_pod_html(self):
        """Perform templating on POD's html results page.

        A wrapper for :func:`~util_mdtf.append_html_template`. 
        """
        config = util_mdtf.ConfigManager()
        source = os.path.join(self.POD_CODE_DIR, self.name+'.html')
        dest = os.path.join(self.POD_WK_DIR, self.name+'.html')

        template = config.global_envvars.copy()
        template.update(self.pod_env_vars)
        if self.name == 'convective_transition_diag':
            # change filenames of model and obs figures that get linked
            # need a more elegant way to handle this
            tropo_meas = template.get('BULK_TROPOSPHERIC_TEMPERATURE_MEASURE', None)
            if tropo_meas == '1':
                template['TROPO_VAR'] = 'tave'
            elif tropo_meas == '2':
                template['TROPO_VAR'] = 'qsat_int'
            else:
                print(("ERROR in convective_transition_diag's settings.jsonc: "
                    "BULK_TROPOSPHERIC_TEMPERATURE_MEASURE = {}, expected '1' "
                    "or '2'").format(tropo_meas))

        if os.path.exists(dest):
            os.remove(dest)
        util_mdtf.append_html_template(source, dest, template_dict=template)

    def append_result_link(self, error=None):
        """Update the top level index.html page with a link to this POD's results.

        This simply appends one of two html fragments to index.html: 
        pod_result_snippet.html if the POD completed successfully, or
        pod_error_snippet.html if an exception was raised during the POD's setup
        or execution.

        Args:
            error (default None): :py:class:`Exception` object (if any) that was
                raised during POD's attempted execution. If this is None, assume
                that POD ran successfully.
        """
        src_dir = os.path.join(self.code_root, 'src', 'html')
        template_dict = self.__dict__.copy()
        if error is None:
            # normal exit
            src = os.path.join(src_dir, 'pod_result_snippet.html')
        else:
            # report error
            src = os.path.join(src_dir, 'pod_error_snippet.html')
            template_dict['error_text'] = str(error)
        util_mdtf.append_html_template(src, self.TEMP_HTML, template_dict)

    def convert_pod_figures(self, subdir):
        """Convert all vector graphics in `POD_WK_DIR/subdir` to .png files using
        ghostscript.

        All vector graphics files (identified by extension) in any subdirectory 
        of `POD_WK_DIR/subdir` are converted to .png files by running 
        `ghostscript <https://www.ghostscript.com/>`__ in a subprocess.
        Ghostscript is included in the _MDTF_base conda environment. Afterwards,
        any bitmap files (identified by extension) in any subdirectory of
        `POD_WK_DIR/subdir` are moved to `POD_WK_DIR/subdir`.

        .. note::
            This effectively flattens any subdirectories in `POD_WK_DIR/subdir`.

        Args:
            subdir: Either `'model'` or `'obs'`. Subdirectory of `POD_WK_DIR` 
                to work in.
        """
        config = util_mdtf.ConfigManager()
        full_subdir = os.path.join(self.POD_WK_DIR, subdir)
        files = util.find_files(
            os.path.join(full_subdir, 'PS'),
            ['*.ps', '*.PS', '*.eps', '*.EPS', '*.pdf', '*.PDF']
        )
        for f in files:
            f_stem, _ = os.path.splitext(os.path.basename(f))
            path_stem = os.path.join(full_subdir, f_stem)
            _ = util.run_shell_command(
                'gs {flags} -sOutputFile="{f_out}" {f_in}'.format(
                flags=config.config.get('convert_flags',''),
                f_in=f,
                f_out=path_stem+'-%d.png'
            ))
            # if .ps file was multiple pages, this will generate 1 png per page.
            # however, page number is included for output from single-page ps 
            # files, and number starts from 1, not 0. Rename files to fix this.
            out_files = glob.glob(path_stem+'-?.png')
            if not out_files:
                print("Error: no png generated for {}".format(f))
            elif len(out_files) == 1:
                shutil.move(out_files[0], path_stem+'.png')
            else:
                for n in list(range(len(out_files))):
                    shutil.move(
                        path_stem+'-{}.png'.format(n+1),
                        path_stem+'-{}.png'.format(n)
                    )
        # move converted figures and any figures saved directly as bitmaps
        files = util.find_files(
            full_subdir, ['*.png', '*.gif', '*.jpg', '*.jpeg']
        )
        for f in files:
            shutil.move(f, os.path.join(full_subdir, os.path.basename(f)))

    def cleanup_pod_files(self):
        """Copy and remove remaining files to `POD_WK_DIR`.

        In order, this 1) copies .pdf documentation (if any) from 
        `POD_CODE_DIR/doc`, 2) copies any bitmap figures in any subdirectory of
        `POD_OBS_DATA` to `POD_WK_DIR/obs` (needed for legacy PODs without 
        digested observational data), 3) removes vector graphics if requested,
        4) removes netCDF scratch files in `POD_WK_DIR` if requested.

        Settings are set at runtime, when :class:`~util_mdtf.ConfigManager` is 
        initialized.
        """
        config = util_mdtf.ConfigManager()
        # copy PDF documentation (if any) to output
        files = util.find_files(os.path.join(self.POD_CODE_DIR, 'doc'), '*.pdf')
        for f in files:
            shutil.copy2(f, self.POD_WK_DIR)

        # copy premade figures (if any) to output 
        files = util.find_files(
            self.POD_OBS_DATA, ['*.gif', '*.png', '*.jpg', '*.jpeg']
        )
        for f in files:
            shutil.copy2(f, os.path.join(self.POD_WK_DIR, 'obs'))

        # remove .eps files if requested
        if not config.config.save_ps:
            for d in ['model', 'obs']:
                if os.path.exists(os.path.join(self.POD_WK_DIR, d, 'PS')):
                    shutil.rmtree(os.path.join(self.POD_WK_DIR, d, 'PS'))
        # delete netCDF files, keep everything else
        if config.config.save_non_nc:
            for f in util.find_files(self.POD_WK_DIR, '*.nc'):
                os.remove(f)
        # delete all generated data (flag is a misnomer)
        elif not config.config.save_nc:
            for d in ['model', 'obs']:
                if os.path.exists(os.path.join(self.POD_WK_DIR, d, 'netCDF')):
                    shutil.rmtree(os.path.join(self.POD_WK_DIR, d, 'netCDF'))
