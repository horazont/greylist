#!/usr/bin/python3
import logging
import sys

logging.basicConfig(
    level=logging.DEBUG,
    stream=sys.stderr)

import greylist

if __name__ == "__main__":
    while True:
        attrs = greylist.read_request(sys.stdin)
        if attrs is None:
            break
        greylist.clean_request(attrs)
        if greylist.process_request(attrs):
            print(greylist.response_pass)
        else:
            print(greylist.response_fail)
        greylist.gc_db()
