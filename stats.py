#!/usr/bin/python3
from datetime import datetime, timedelta
import os
import stat

def do_config_for_listtype(listtype, order):
    print("graph_title {} contents".format(listtype))
    print("graph_vlabel Entries")
    print("graph_category mail")
    print("graph_info Statistics about the activity of the {}".format(listtype))
    print("graph_order {}".format(" ".join(order)))

def do_config_greylist():
    do_config_for_listtype("greylist",
                           order=["dead", "inactive", "active", "total"])
    print("dead.label dead")
    print("dead.draw AREA")
    print("dead.info Entries which have not been touched since their creation"
          " and are older than {} seconds".format(greylist.stats_dead_threshold))
    print("inactive.label inactive")
    print("inactive.draw STACK")
    print("inactive.info Stale entries in the greylist")
    print("active.label active")
    print("active.draw STACK")
    print("active.info Recently used entries in the greylist")
    print("total.label total")
    print("total.draw LINE2")
    print("total.info Total entries in the greylist")

def do_data_greylist(cursor):
    active = get_active_greylist(cursor)
    total = get_total("greylist", cursor)
    dead = get_dead_greylist(cursor)
    print("dead.value {}".format(dead))
    print("active.value {}".format(active))
    print("inactive.value {}".format(total-(active+dead)))
    print("total.value {}".format(total))

def do_config_whitelist():
    do_config_for_listtype("whitelist",
                           order=["inactive", "active", "pending", "total"])
    print("inactive.label inactive")
    print("inactive.draw AREA")
    print("inactive.info Stale entries in the whitelist")
    print("active.label active")
    print("active.draw STACK")
    print("active.info Recently used entries in the whitelist")
    print("pending.label pending")
    print("pending.draw STACK")
    print("pending.info Whitelist entries for which the hit count threshold has"
          " not been reached yet")
    print("total.label total")
    print("total.draw LINE2")
    print("total.info Total entries in the greylist")

def do_data_whitelist(cursor):
    active = get_active_whitelist(cursor)
    pending = get_pending_whitelist(cursor)
    total = get_total("whitelist", cursor)
    print("active.value {}".format(active))
    print("inactive.value {}".format(total-(active+pending)))
    print("pending.value {}".format(pending))
    print("total.value {}".format(total))

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
    print("greylist.value {}".format(
        get_total("greylist", cursor)))
    print("whitelist.value {}".format(
        get_total("whitelist", cursor)))

def do_config_size():
    print("graph_title greylisting database size")
    print("graph_vlabel bytes")
    print("graph_category mail")
    print("graph_info Size of the greylisting sqlite database")
    print("graph_args --base 1024")
    print("graph_order size")
    print("size.label size")
    print("size.draw LINE1")
    print("size.info Size of the SQLite file")

def do_data_size(cursor):
    print("size.value {}".format(get_db_size()))

def do_config_client_names():
    print("graph_title Distinct client names")
    print("graph_vlabel Names")
    print("graph_category mail")
    print("graph_info Distinct client names in the greylisting component")
    print("graph_order clientnames")
    print("clientnames.label clientnames")
    print("clientnames.draw LINE1")
    print("clientnames.info Distinct client names in the greylisting component")

def do_data_client_names(cursor):
    print("clientnames.value {}".format(
        get_distinct_client_names(cursor)))

def do_config_overhead():
    print("graph_title Greylist database overhead")
    print("graph_vlabel bytes/entry")
    print("graph_category mail")
    print("graph_info Plot the amount of bytes per entry in the greylisting database. Whitelist and Greylist entries are counted equally.")
    print("graph_args --base 1024")
    print("graph_order efficiency")
    print("efficiency.label efficiency")
    print("efficiency.draw LINE1")
    print("efficiency.info Ratio of database size and entry count.")

def do_data_overhead(cursor):
    count = get_total("greylist", cursor) + get_total("whitelist", cursor)
    efficiency = get_db_size() / count
    print("efficiency.value {:.4f}".format(efficiency))

def get_total(listtype, cursor):
    # listtype is not direct user input, so format is safe here
    total, = cursor.execute(
        """SELECT COUNT(*) FROM {}""".format(listtype)).fetchone()
    return total

def get_active_greylist(cursor):
    now = datetime.utcnow()
    active, = cursor.execute(
        """SELECT COUNT(*) FROM greylist
        WHERE (julianday(?) - julianday(last_seen)) * 86400.0 <= ?""",
        (now, greylist.stats_active_threshold)).fetchone()
    return active

def get_active_whitelist(cursor):
    now = datetime.utcnow()
    active, = cursor.execute(
        """SELECT COUNT(*) FROM whitelist
        WHERE (julianday(?) - julianday(last_seen)) * 86400.0 <= ?
        AND hit_count >= ?""",
        (now,
         greylist.stats_active_threshold,
         greylist.auto_whitelist_threshold)).fetchone()
    return active

def get_dead_greylist(cursor):
    now = datetime.utcnow()
    dead, = cursor.execute(
        """SELECT COUNT(*) FROM greylist
        WHERE (julianday(?) - julianday(last_seen)) * 86400.0 >= ?
        AND last_seen = first_seen""",
        (now,
         greylist.stats_dead_threshold)).fetchone()
    return dead

def get_pending_whitelist(cursor):
    pending, = cursor.execute(
        """SELECT COUNT(*) FROM whitelist
        WHERE hit_count < ?""",
        (greylist.auto_whitelist_threshold,)).fetchone()
    return pending

def get_distinct_client_names(cursor):
    count, = cursor.execute(
        """SELECT COUNT(*) FROM (
        SELECT COUNT(*) FROM greylist GROUP BY client_name
        )""").fetchone()
    return count

def get_db_size():
    greylist.close_db()
    st = os.stat(greylist.db_file)
    return st.st_size

graph_types = {
    "greylist": (do_config_greylist, do_data_greylist),
    "whitelist": (do_config_whitelist, do_data_whitelist),
    "overview": (do_config_overview, do_data_overview),
    "client_names": (do_config_client_names, do_data_client_names),
    "size": (do_config_size, do_data_size),
    "overhead": (do_config_overhead, do_data_overhead)
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

    print("total_greylist {}".format(get_total("greylist", cursor)))
    print("active_greylist {}".format(get_active_greylist(cursor)))
    print("dead_greylist {}".format(get_dead_greylist(cursor)))
    print("total_whitelist {}".format(get_total("whitelist", cursor)))
    print("active_whitelist {}".format(get_active_whitelist(cursor)))
    print("pending_whitelist {}".format(get_pending_whitelist(cursor)))
    print("distinct_greylist_client_names {}".format(
        get_distinct_client_names(cursor)))
    print("db_size {}".format(get_db_size()))
