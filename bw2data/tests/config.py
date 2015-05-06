# -*- coding: utf-8 -*-
from __future__ import print_function, unicode_literals
from eight import *

import os
from . import BW2DataTest
from .. import config
import json


class ConfigTest(BW2DataTest):
    # def test_request_directory_not_writable(self):
    #     dirpath = config.request_dir("untouchable")
    #     os.chmod(dirpath, 000)
    #     self.assertFalse(config.request_dir("untouchable"))
    #     os.chmod(dirpath, 776)

    def test_request_directory(self):
        self.assertTrue(config.request_dir("wow"))
        self.assertTrue(config.request_dir(u"привет"))

    def test_basic_preferences(self):
        config.load_preferences()
        self.assertEqual({}, config.p)

    def test_save_preferences(self):
        config.load_preferences()
        config.p['saved'] = "yep"
        config.save_preferences()
        self.assertEqual(config.p['saved'], "yep")
        config.load_preferences()
        self.assertEqual(config.p['saved'], "yep")

    def test_default_biosphere(self):
        self.assertEqual(config.biosphere, "biosphere3")

    def test_default_geo(self):
        self.assertEqual(config.global_location, "GLO")

    def test_set_retrieve_biosphere(self):
        config.p['biosphere_database'] = "foo"
        config.save_preferences()
        config.load_preferences()
        self.assertEqual(config.biosphere, "foo")
        del config.p['biosphere_database']
        config.save_preferences()
