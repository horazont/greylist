#!/usr/bin/python3
from datetime import datetime, timedelta

if __name__ == "__main__":
    import argparse
    import logging
    import sys

    parser = argparse.ArgumentParser(
        description="""Extract some figures from a greylisting database for
        statistical purposes."""
    )
    parser.add_argument(
        "-c", "--config",
        default=None,
        type=argparse.FileType("r"),
        metavar="FILE",
        help="Specify a config file to override defaults")
    parser.add_argument(
        "-v",
        dest="verbosity",
        action="count",
        default=0,
        help="Increase verbosity by one step")

    args = parser.parse_args()

    verbosity = {
        0: logging.ERROR,
        1: logging.WARN,
        2: logging.INFO,
        3: logging.DEBUG
    }

    logging.basicConfig(
        level=verbosity.get(args.verbosity, logging.DEBUG),
        stream=sys.stderr)

    import greylist
    if args.config is not None:
        greylist.load_config(args.config)

    dbconn = greylist.get_db()
    cursor = dbconn.cursor()
    now = datetime.utcnow()

    try:
        active_greylist, = cursor.execute(
            """SELECT COUNT(*) FROM greylist
            WHERE (julianday(?) - julianday(last_seen)) * 86400.0 <= ?""",
            (now, greylist.stats_active_threshold)).fetchone()
        total_greylist, = cursor.execute(
            """SELECT COUNT(*) FROM greylist""").fetchone()
        active_whitelist, = cursor.execute(
            """SELECT COUNT(*) FROM whitelist
            WHERE (julianday(?) - julianday(last_seen)) * 86400.0 <= ?""",
            (now, greylist.stats_active_threshold)).fetchone()
        total_whitelist, = cursor.execute(
            """SELECT COUNT(*) FROM whitelist""").fetchone()
        distinct_greylist_client_names, = cursor.execute(
            """SELECT COUNT(*) FROM (
                SELECT COUNT(*) FROM greylist GROUP BY client_name
            )""").fetchone()
    finally:
        cursor.close()
        dbconn.close()

    print("active_greylist={}".format(active_greylist))
    print("total_greylist={}".format(total_greylist))
    print("active_whitelist={}".format(active_whitelist))
    print("total_whitelist={}".format(total_whitelist))
    print("distinct_greylist_client_names={}".format(
        distinct_greylist_client_names))
