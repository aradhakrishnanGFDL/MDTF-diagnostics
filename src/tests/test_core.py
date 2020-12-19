import os
import unittest
from collections import namedtuple
import itertools
import unittest.mock as mock # define mock os.environ so we don't mess up real env vars
import src.core as core
from src.data_manager import DataManager
from src.diagnostic import Diagnostic
from subprocess import CalledProcessError
from src.tests.shared_test_utils import setUp_config_singletons, tearDown_config_singletons


class TestVariableTranslator(unittest.TestCase):
    def setUp(self):
        # set up translation dictionary without calls to filesystem
        setUp_config_singletons()

    def tearDown(self):
        # call _reset method deleting clearing Translator for unit testing, 
        # otherwise the second, third, .. tests will use the instance created 
        # in the first test instead of being properly initialized
        tearDown_config_singletons()

    def test_variabletranslator(self):
        temp = core.VariableTranslator()
        temp.add_convention({
            'name':'not_CF', 'axes': {},
            'variables':{
                'PRECT': {"standard_name": "pr_var", "units": "1"},
                'PRECC': {"standard_name": "prc_var", "units": "1"}
            }
        })
        self.assertEqual(temp.name_to_CF('not_CF', 'PRECT'), 'pr_var')
        self.assertEqual(temp.name_from_CF('not_CF', 'pr_var'), 'PRECT')

    def test_variabletranslator_no_key(self):
        temp = core.VariableTranslator()
        temp.add_convention({
            'name':'not_CF', 'axes': {},
            'variables':{
                'PRECT': {"standard_name": "pr_var", "units": "1"},
                'PRECC': {"standard_name": "prc_var", "units": "1"}
            }
        })
        self.assertRaises(KeyError, temp.name_to_CF, 'B', 'PRECT')
        self.assertRaises(KeyError, temp.name_to_CF, 'not_CF', 'nonexistent_var')
        self.assertRaises(KeyError, temp.name_from_CF, 'B', 'PRECT')
        self.assertRaises(KeyError, temp.name_from_CF, 'not_CF', 'nonexistent_var')

    def test_variabletranslator_aliases(self):
        # create multiple entries when multiple models specified
        temp = core.VariableTranslator()
        temp.add_convention({
            'name':'not_CF', 'axes': {},
            'models': ['A', 'B'],
            'variables':{
                'PRECT': {"standard_name": "pr_var", "units": "1"},
                'PRECC': {"standard_name": "prc_var", "units": "1"}
            }
        })
        self.assertEqual(temp.name_from_CF('not_CF', 'pr_var'), 'PRECT')
        self.assertEqual(temp.name_from_CF('A','pr_var'), 'PRECT')
        self.assertEqual(temp.name_from_CF('B','pr_var'), 'PRECT')

class TestVariableTranslatorFiles(unittest.TestCase):
    def tearDown(self):
        # call _reset method deleting clearing Translator for unit testing, 
        # otherwise the second, third, .. tests will use the instance created 
        # in the first test instead of being properly initialized
        tearDown_config_singletons()

    def test_variabletranslator_load_files(self):
        # run in non-unit-test mode to test loading of config files
        cwd = os.path.dirname(os.path.realpath(__file__)) 
        code_root = os.path.dirname(os.path.dirname(cwd))
        raised = False
        try:
            _ = core.VariableTranslator(code_root, unittest=False)
        except Exception:
            raised = True
        self.assertFalse(raised)

class TestPathManager(unittest.TestCase):
    # pylint: disable=maybe-no-member
    def setUp(self):
        # set up translation dictionary without calls to filesystem
        setUp_config_singletons(paths = {
            'CODE_ROOT':'A', 'OBS_DATA_ROOT':'B', 'MODEL_DATA_ROOT':'C',
            'WORKING_DIR':'D', 'OUTPUT_DIR':'E'
        })

    def tearDown(self):
        tearDown_config_singletons()

    # ------------------------------------------------

    def test_pathmgr_global(self):
        paths = core.PathManager()
        self.assertEqual(paths.CODE_ROOT, 'A')
        self.assertEqual(paths.OUTPUT_DIR, 'E')

    @unittest.skip("")
    def test_pathmgr_global_asserterror(self):
        d = {
            'OBS_DATA_ROOT':'B', 'MODEL_DATA_ROOT':'C',
            'WORKING_DIR':'D', 'OUTPUT_DIR':'E'
        }
        paths = core.PathManager()
        self.assertRaises(AssertionError, paths.parse, d, list(d.keys()))
        # initialize successfully so that tear_down doesn't break
        #_ = core.PathManager(unittest = True) 


@mock.patch.multiple(DataManager, __abstractmethods__=set())
class TestPathManagerPodCase(unittest.TestCase):
    def setUp(self):
        # set up translation dictionary without calls to filesystem
        setUp_config_singletons(
            config=self.case_dict, 
            paths={
                'CODE_ROOT':'A', 'OBS_DATA_ROOT':'B', 'MODEL_DATA_ROOT':'C',
                'WORKING_DIR':'D', 'OUTPUT_DIR':'E'
            },
            pods={ 'AA':{
                'settings':{}, 
                'varlist':[{'var_name': 'pr_var', 'freq':'mon'}]
                }
            })

    case_dict = {
        'CASENAME': 'A', 'model': 'B', 'FIRSTYR': 1900, 'LASTYR': 2100,
        'pod_list': ['AA']
    }

    def tearDown(self):
        tearDown_config_singletons()

    def test_pathmgr_model(self):
        paths = core.PathManager()
        case = DataManager(self.case_dict)
        d = paths.model_paths(case)
        self.assertEqual(d['MODEL_DATA_DIR'], 'TEST_MODEL_DATA_ROOT/A')
        self.assertEqual(d['MODEL_WK_DIR'], 'TEST_WORKING_DIR/MDTF_A_1900_2100')

    def test_pathmgr_pod(self):
        paths = core.PathManager()
        case = DataManager(self.case_dict)
        pod = Diagnostic('AA')
        d = paths.pod_paths(pod, case)
        self.assertEqual(d['POD_CODE_DIR'], 'TEST_CODE_ROOT/diagnostics/AA')
        self.assertEqual(d['POD_OBS_DATA'], 'TEST_OBS_DATA_ROOT/AA')
        self.assertEqual(d['POD_WK_DIR'], 'TEST_WORKING_DIR/MDTF_A_1900_2100/AA')



# ---------------------------------------------------

if __name__ == '__main__':
    unittest.main()