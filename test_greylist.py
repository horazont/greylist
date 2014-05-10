import time
import unittest

import greylist
greylist.db_file = ":memory:"

class TestGreylist(unittest.TestCase):
    def setUp(self):
        greylist.get_db()

    def test_greylisting(self):
        request = {
            "client_name": "example.com",
            "sender": "foo@dom1.example.com",
            "recipient": "bar@dom2.example.com"
        }

        greylist.greylist_timeout = 1

        self.assertEqual(
            greylist.FAILED,
            greylist.process_request(request))

        time.sleep(1)

        self.assertEqual(
            greylist.PASSED,
            greylist.process_request(request))

        greylist.greylist_timeout = 100

        self.assertEqual(
            greylist.FAILED,
            greylist.process_request(request))

    def test_whitelisting(self):
        request = {
            "client_name": "example.com",
            "sender": "foo@dom1.example.com",
            "recipient": "bar@dom2.example.com"
        }

        greylist.greylist_timeout = 1
        greylist.auto_whitelist_threshold = 2

        self.assertEqual(
            greylist.FAILED,
            greylist.process_request(request))

        time.sleep(1)

        self.assertEqual(
            greylist.PASSED,
            greylist.process_request(request))

        self.assertEqual(
            greylist.PASSED,
            greylist.process_request(request))

        self.assertEqual(
            greylist.PASSED,
            greylist.process_request(request))

        greylist.greylist_timeout = 100

        self.assertEqual(
            greylist.PASSED,
            greylist.process_request(request))

    def test_move_to_whitelist(self):
        request = {
            "client_name": "example.com",
            "sender": "foo@dom1.example.com",
            "recipient": "bar@dom2.example.com"
        }

        greylist.greylist_timeout = 1
        greylist.auto_whitelist_threshold = 1
        greylist.move_to_whitelist = True

        self.assertEqual(
            greylist.FAILED,
            greylist.process_request(request))

        time.sleep(1)

        self.assertEqual(
            greylist.PASSED,
            greylist.process_request(request))

        self.assertEqual(
            greylist.PASSED,
            greylist.process_request(request))

        self.assertSequenceEqual(
            [(0,)],
            list(greylist.get_db().cursor().execute(
                "SELECT COUNT(*) FROM greylist")))


    def tearDown(self):
        greylist.close_db()
