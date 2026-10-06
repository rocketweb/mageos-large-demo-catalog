import sys
from pathlib import Path
import subprocess
import unittest
import json
from unittest.mock import MagicMock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import verify_expansion_browser as browser


class ExistingTunnelTest(unittest.TestCase):
    def test_forward_reuses_the_master_without_expectation_of_a_live_child_process(self):
        with patch.object(browser.subprocess,'run',return_value=subprocess.CompletedProcess([],0)),patch.object(browser.socket,'create_connection'):
            cancel=browser.open_existing_tunnel(18986)
        self.assertIn('cancel',cancel)
        self.assertIn('127.0.0.1:18986',cancel)
        self.assertNotIn('-N',cancel)

    def test_forward_failure_is_reported_before_browser_launch(self):
        with patch.object(browser.subprocess,'run',side_effect=[subprocess.CompletedProcess([],0),subprocess.CompletedProcess([],255)]):
            with self.assertRaises(RuntimeError):browser.open_existing_tunnel(18986)


class ConfigurableControlsTest(unittest.TestCase):
    def exercise(self, radios=True, disabled=False):
        with __import__('tempfile').TemporaryDirectory() as tmp:
            output=Path(tmp)
            controls=[{'name':'super_attribute[93]','kind':'radio','id':'color-black','value':'90','label':'Black','disabled':disabled},
                      {'name':'super_attribute[160]','kind':'select','id':'size','value':'104','label':'Small','disabled':False}]
            actions=[];chosen=[]
            def command(argv,**kwargs):
                action=argv[4:]  # agent-browser, --session, name, --json
                # The Studio resolver flags are present after --json.
                if action[:1]==['--args']:action=action[2:]
                name=action[0];actions.append(action)
                if name=='eval':
                    js=action[1]
                    if 'header a' in js:value=[]
                    elif 'image_loaded' in js:value={'name':'Fixture','image_loaded':True,'form':True,'options':[]}
                    elif 'Required variant option unavailable' in js:
                        # This is the old select-only implementation: it misses Black.
                        value=['Small']
                    elif 'selectedOptions' in js:value=chosen.copy()
                    else:value=controls if radios else controls[1:]
                    data={'result':value}
                elif name=='check':chosen.append('Black');data={}
                elif name=='select':chosen.append('Small');data={}
                else:data={}
                return subprocess.CompletedProcess(argv,0,json.dumps({'success':True,'data':data}), '')
            case={'sku':'fixture','name':'Fixture','url':'http://relevance.comtom.lab:8080/fixture.html',
                  'image':'/fixture.jpg','type':'configurable','options':{'color':'Black','wands_size':'Small'}}
            with patch.object(browser.subprocess,'run',side_effect=command):
                result=browser.browser_acceptance(browser.LOCAL,[case],output,full=False)
            return result,actions

    def test_mixed_radio_swatches_and_size_dropdown_can_select_a_complete_variant(self):
        result,actions=self.exercise()
        self.assertTrue(result['passed'])
        self.assertIn(['check','#color-black'],actions)
        self.assertIn(['select','#size','104'],actions)
        self.assertEqual(result['checks'][0]['selected_labels'],['Black','Small'])

    def test_missing_color_control_is_not_accepted(self):
        with self.assertRaises(ValueError):self.exercise(radios=False)

    def test_disabled_color_option_is_not_accepted(self):
        with self.assertRaises(ValueError):self.exercise(disabled=True)
