#!/usr/bin/python3
from datetime import datetime, timedelta

def do_config_for_listtype(listtype):
    print("graph_title {} contents".format(listtype))
    print("graph_vlabel Entries")
    print("graph_category mail")
    print("graph_info Statistics about the activity of the {}".format(listtype))
    print("graph_order active inactive total")
    print("active.label active")
    print("active.draw AREA")
    print("active.info Recently used entries in the {}".format(listtype))
    print("inactive.label inactive")
    print("inactive.draw STACK")
    print("inactive.info Stale entries in the {}".format(listtype))
    print("total.label Total entries")
    print("total.draw LINE2")
    print("total.info Total entries in the {}".format(listtype))

def do_data_for_listtype(listtype, cursor):
    active = get_active(listtype, cursor)
    total = get_total(listtype, cursor)
    print("active {}".format(active))
    print("inactive {}".format(total-active))
    print("total {}".format(total))

def do_config_greylist():
    do_config_for_listtype("greylist")

def do_data_greylist(cursor):
    do_data_for_listtype("greylist", cursor)

def do_config_whitelist():
    do_config_for_listtype("whitelist")

def do_data_whitelist(cursor):
    do_data_for_listtype("whitelist", cursor)

def do_config_overview():
    print("graph_title Greylisting stats")
    print("graph_vlabel Entries")
    print("graph_category mail")
    print("graph_info Statistics about different components of the greylisting"
          " system")
    print("graph_order greylist whitelist")
    print("greylist.label greylist")
    print("greylist.draw LINE2")
    print("greylist.info Amount of entries in the greylist")
    print("whitelist.label whitelist")
    print("whitelist.draw LINE2")
    print("whitelist.info Amount of entries in the whitelist")

def do_data_overview(cursor):
    print("greylist {}".format(
        get_total("greylist", cursor)))
    print("whitelist {}".format(
        get_total("whitelist", cursor)))

def do_config_client_names():
    print("graph_title Distinct client names")
    print("graph_vlabel Names")
    print("graph_category mail")
    print("graph_info Distinct client names in the greylisting component")
    print("graph_order clientnames")
    print("clientnames.label clientnames")
    print("clientnames.draw LINE2")
    print("clientnames.info Distinct client names in the greylisting component")

def do_data_client_names(cursor):
    print("clientnames {}".format(
        get_distinct_client_names(cursor)))

def get_total(listtype, cursor):
    # listtype is not direct user input, so format is safe here
    total, = cursor.execute(
        """SELECT COUNT(*) FROM {}""".format(listtype)).fetchone()
    return total

def get_active(listtype, cursor):
    # listtype is not direct user input, so format is safe here
    now = datetime.utcnow()
    active, = cursor.execute(
        """SELECT COUNT(*) FROM {}
        WHERE (julianday(?) - julianday(last_seen)) * 86400.0 <= ?""".format(
            listtype),
        (now, greylist.stats_active_threshold)).fetchone()
    return active

def get_distinct_client_names(cursor):
    count, = cursor.execute(
        """SELECT COUNT(*) FROM (
        SELECT COUNT(*) FROM greylist GROUP BY client_name
        )""").fetchone()
    return count

graph_types = {
    "greylist": (do_config_greylist, do_data_greylist),
    "whitelist": (do_config_whitelist, do_data_whitelist),
    "overview": (do_config_overview, do_data_overview),
    "client_names": (do_config_client_names, do_data_client_names)
}

if __name__ == "__main__":
    import argparse
    import logging
    import os
    import sys

    parser = argparse.ArgumentParser(
        description="""Extract some figures from a greylisting database for
        statistical purposes. If the MUNIN environment variable is set, the
        CONFIG environment variable is treadet as if it was passed to
        --config. --config, if set still takes precedence."""
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
    parser.add_argument(
        "munin_command",
        default=None,
        nargs="?",
        metavar="MUNINCOMMAND",
        choices={"config"},
        help="Writes a config suitable for munin to stdout")

    args = parser.parse_args()

    if "MUNIN" in os.environ and not args.config:
        filename = os.environ.get("CONFIG", None)
        if filename is not None:
            args.config = open(filename, "r")
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

    logger = logging.getLogger("stats")

    if "MUNIN" in os.environ:
        try:
            graph_type = os.environ["MUNIN_GRAPH"]
        except KeyError:
            filename = os.path.basename(sys.argv[0])
            prefix, _, graph_type = filename.partition("_")
            if prefix != "greylisting":
                logger.error("invalid filename: %s", filename)
                sys.exit(1)

        try:
            config_handler, data_handler = graph_types[graph_type]
        except KeyError as err:
            logger.error("unknown graph type: %s", err)
            sys.exit(1)

        if args.munin_command == "config":
            config_handler()
            sys.exit(0)

        dbconn = greylist.get_db()
        cursor = dbconn.cursor()
        data_handler(cursor)
        sys.exit(0)

    dbconn = greylist.get_db()
    cursor = dbconn.cursor()

    for listtype in ["greylist", "whitelist"]:
        print("total_{} {}".format(
            listtype, get_total(listtype, cursor)))
        print("active_{} {}".format(
            listtype, get_active(listtype, cursor)))
    print("distinct_greylist_client_names {}".format(
        get_distinct_client_names(cursor)))
