#!/usr/bin/python3
import itertools

def show_greylist(args):
    dbconn = greylist.get_db()
    sqlargs = ()
    sql = ("SELECT id, client_name, sender, recipient, first_seen, last_seen "
           "FROM greylist "
           "ORDER BY recipient ASC, sender ASC, last_seen DESC")
    if args.limit is not None:
        sql += " LIMIT ?"
        sqlargs += (args.limit,)
    cursor = dbconn.execute(sql, sqlargs)
    rows = itertools.groupby(cursor, lambda x: x[3])
    for recipient, items in rows:
        print("recipient: {}".format(recipient))
        for id, client_name, sender, _, first_seen, last_seen in items:
            print("    #{:<4d} {:30s} (from {})\n        first: {}\n        last:  {}".format(
                id, sender, client_name,
                first_seen.replace(microsecond=0),
                last_seen.replace(microsecond=0)))

def show_whitelist(args):
    dbconn = greylist.get_db()
    sqlargs = ()
    sql = ("SELECT id, client_name, last_seen "
           "FROM whitelist "
           "ORDER BY client_name ASC, last_seen DESC")
    if args.limit is not None:
        sql += " LIMIT ?"
        sqlargs += (args.limit,)
    cursor = dbconn.execute(sql, sqlargs)
    for id, client_name, last_seen in cursor:
        print("#{:<4d} {:40s} {!s:20s}".format(
            id,
            client_name,
            last_seen.replace(microsecond=0)))

if __name__ == "__main__":
    import argparse
    import logging
    import os
    import sys

    parser = argparse.ArgumentParser(
        description="""Extract some information from the greylist database"""
    )
    parser.add_argument(
        "-v",
        dest="verbosity",
        action="count",
        default=0,
        help="Increase verbosity by one step")
    parser.add_argument(
        "-c", "--config",
        default=None,
        type=argparse.FileType("r"),
        metavar="FILE",
        help="Specify a config file to override defaults")
    subcommands = parser.add_subparsers(
        title="Commands")

    cmd_show_greylist = subcommands.add_parser("show-greylist")
    cmd_show_greylist.set_defaults(func=show_greylist)
    cmd_show_greylist.add_argument(
        "-l", "--limit",
        type=int,
        help="Limit the amount of rows returned",
        metavar="COUNT")

    cmd_show_whitelist = subcommands.add_parser("show-whitelist")
    cmd_show_whitelist.set_defaults(func=show_whitelist)
    cmd_show_whitelist.add_argument(
        "-l", "--limit",
        type=int,
        help="Limit the amount of rows returned",
        metavar="COUNT")

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

    if args.config:
        greylist.load_config(args.config)

    args.func(args)
