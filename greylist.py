#!/usr/bin/python3
import logging
import sqlite3

from datetime import datetime, timedelta

class RESPONSE:
    def __init__(self, name):
        self.name = name

    def __str__(self):
        return self.name

    def __repr__(self):
        return "<response={}>".format(self.name)

PASSED = RESPONSE("PASSED")
FAILED = RESPONSE("FAILED")

del RESPONSE

# CONFIGURATION

# greylisting happens on triples of (sender, recipient, client_name).
# whitelisting happens on client_name
# client name is either the client_name (hostname) supplied or the
# client_address, if no name was supplied

# these values are defaults. they can be configured by passing a INI-style
# config file via --config, in the [DEFAULT] section

# If more than the given number of requests have been made by a given
# client_name which have passed the greylisting check, the address is added to
# the whitelist. Set this to None to disable auto-whitelisting.
auto_whitelist_threshold = 10

# The time which has to pass since the first occurence of a greylisting triple
# for mail to be accepted.
greylist_timeout = 10

# If the greylist database entry count supersedes this number, entries are
# removed so that the limit is satisfied again. The entries are deleted in the
# order of last_seen, from oldest to newest. Set to None to disable this limit.
max_greylist_entries = 10000

# Same as max_greylist_entries, but for whitelists.
max_whitelist_entries = 1000

# Greylist entries are removed if they have not been used after the given amount
# of seconds. This will also remove entries from whitelisted domains, because
# they are not touched while whitelisting is in place. Set this to None to
# disable this limit.
greylist_expire = None

# Same as greylist_expire, but for the whitelist.
whitelist_expire = None

# Maximum time (in seconds) since last_seen for greylist and whitelist entries
# to count as active
stats_active_threshold = 3600

# action=dunno will only permit if no other rule denies
response_pass = "action=dunno\n"

# action=defer_if_permit will defer the mail if no rule denies it
response_fail = "action=defer_if_permit You have been greylisted.\n"

# END OF CONFIGURATION

SCHEMA = {}
SCHEMA[("table", "whitelist")] = """CREATE TABLE whitelist
   (
      id INTEGER PRIMARY KEY,
      client_name TEXT,
      last_seen TIMESTAMP,
      hit_count INTEGER,
      CONSTRAINT client_name UNIQUE (client_name)
   )"""
SCHEMA[("table", "greylist")] = """CREATE TABLE greylist
   (
      id INTEGER PRIMARY KEY,
      client_name TEXT,
      sender TEXT,
      recipient TEXT,
      first_seen TIMESTAMP,
      last_seen TIMESTAMP,
      CONSTRAINT match UNIQUE (client_name, sender, recipient)
  )"""
SCHEMA[("index", "whitelist_last_seen")] = """CREATE INDEX whitelist_last_seen ON greylist (last_seen)"""
SCHEMA[("index", "greylist_last_seen")] = """CREATE INDEX greylist_last_seen ON greylist
(last_seen)"""

_dbconn = None

def clean_request(attrs):
    if "client_name" not in attrs:
        attrs["client_name"] = attrs["client_address"]

def create_db(dbconn):
    logger.info("(re-)creating database")
    tables = ((table, sql)
              for (type_, table), sql in SCHEMA.items()
              if type_ == "table")
    for table, sql in tables:
        logger.info("creating table %s", table)
        dbconn.execute("DROP TABLE IF EXISTS {}".format(table))
        dbconn.execute(sql)
        logger.info("created table %s", table)

    indicies = ((index, sql)
                for (type_, index), sql in SCHEMA.items()
                if type_ == "index")
    for index, sql in indicies:
        logger.info("creating index %s", index)
        dbconn.execute(sql)
        logger.info("created index %s", index)

def get_db():
    global _dbconn
    if _dbconn is None:
        logger.debug("opening database")
        _dbconn = sqlite3.connect("greylist.db",
                                  detect_types=sqlite3.PARSE_DECLTYPES)
        setup_db(_dbconn)
    return _dbconn

def getint_or_none(config, section, option, fallback):
    try:
        v = config.get(section, option).lower()
    except configparser.NoOptionError:
        return fallback
    if v in {"none", "off", "disabled"}:
        return None
    return int(v)

def getresponse(config, section, option, fallback):
    try:
        v = config.get(section, option).upper()
    except configparser.NoOptionError:
        return fallback

    try:
        return {
            "PASSED": PASSED,
            "FAILED": FAILED
        }[v]
    except ValueError:
        raise ValueError("Invalid response type: {}".format(v))

def gc_db():
    dbconn = get_db()
    cursor = dbconn.cursor()
    now = datetime.utcnow()
    try:
        if greylist_expire is not None:
            cursor.execute("DELETE FROM greylist WHERE (julianday(?) - julianday(last_seen))*86400.0 >= ?",
                           (now, greylist_expire))
            if cursor.rowcount > 0:
                logger.info("removed %s greylist entries due to expiry",
                             cursor.rowcount)

        if whitelist_expire is not None:
            cursor.execute("""DELETE FROM whitelist
            WHERE (julianday(?) - julianday(last_seen))*86400.0 >= ?""",
                           (now, whitelist_expire))
            if cursor.rowcount > 0:
                logger.info("removed %s whitelist entries due to expiry",
                             cursor.rowcount)

        if dbconn.in_transaction:
            dbconn.commit()

        if max_greylist_entries is not None:
            cursor.execute("SELECT COUNT(*) FROM greylist")
            count, = cursor.fetchone()
            if count > max_greylist_entries:
                to_purge = count - max_greylist_entries
                logger.info("purging %s entries from greylist (oversized)",
                             to_purge)
                cursor.execute("""DELETE FROM greylist WHERE id IN (
                SELECT id FROM greylist ORDER BY last_seen ASC LIMIT ?)""",
                               (to_purge,))

        if max_whitelist_entries is not None:
            cursor.execute("SELECT COUNT(*) FROM whitelist")
            count, = cursor.fetchone()
            if count > max_whitelist_entries:
                to_purge = count - max_whitelist_entries
                logger.info("purging %s entries from whitelist (oversized)",
                             to_purge)
                cursor.execute("""DELETE FROM whitelist WHERE id IN (
                SELECT id FROM whitelist ORDER BY last_seen ASC LIMIT ?)""",
                               (to_purge,))


        if dbconn.in_transaction:
            dbconn.commit()
    finally:
        if dbconn.in_transaction:
            dbconn.commit()
        cursor.close()

def load_config(f):
    global auto_whitelist_threshold, max_greylist_entries
    global max_whitelist_entries, greylist_expire, whitelist_expire
    global stats_active_threshold, response_pass, response_fail
    config = configparser.ConfigParser()
    with f as f:
        config.read_file(f)

    auto_whitelist_threshold = getint_or_none(
        config,
        "DEFAULT", "auto_whitelist_threshold",
        fallback=auto_whitelist_threshold)

    max_greylist_entries = getint_or_none(
        config,
        "DEFAULT", "max_greylist_entries",
        fallback=max_greylist_entries)

    max_whitelist_entries = getint_or_none(
        config,
        "DEFAULT", "max_whitelist_entries",
        fallback=max_whitelist_entries)

    greylist_expire = getint_or_none(
        config,
        "DEFAULT", "greylist_expire",
        fallback=greylist_expire)

    whitelist_expire = getint_or_none(
        config,
        "DEFAULT", "whitelist_expire",
        fallback=whitelist_expire)

    stats_active_threshold = getint_or_none(
        config,
        "DEFAULT", "stats_active_threshold",
        fallback=stats_active_threshold)

    response_pass = getint_or_none(
        config,
        "DEFAULT", "response_pass",
        fallback=response_pass)

    response_fail = getint_or_none(
        config,
        "DEFAULT", "response_fail",
        fallback=response_fail)

def read_request(instream):
    attrs = {}
    for line in map(str.strip, instream):
        if not line:
            break
        lhs, _, rhs = line.partition("=")
        if not _:
            raise ValueError("Input format violation")
        attrs[lhs] = rhs
    else:
        return None
    return attrs

def _check_whitelist(cursor, client_name):
    if auto_whitelist_threshold is not None:
        cursor.execute("SELECT hit_count FROM whitelist WHERE client_name=?",
                       (client_name,))
        match = cursor.fetchone()
        if match is not None:
            hit_count, = match
            if hit_count >= auto_whitelist_threshold:
                logger.debug("whitelist check: client_name=%r succeeded",
                              client_name)
                return True
    return False

def _check_greylist(dbconn, cursor, sender, recipient, client_name):
    key = sender, recipient, client_name
    now = datetime.utcnow()
    cursor.execute("""SELECT first_seen FROM greylist
    WHERE sender=? AND recipient=? AND client_name=?""",
                   key)

    match = cursor.fetchone()
    if match is None:
        logger.debug("greylist check: no match, creating new entry")
        # no entry yet
        cursor.execute("""INSERT INTO greylist (sender, recipient, client_name,
        first_seen, last_seen)
        VALUES (?, ?, ?, ?, ?)""",
                       key + (now, now))
        cursor.close()
        dbconn.commit()
        return FAILED
    else:
        first_seen, = match
        logger.debug("greylist check: match, first_seen=%s", first_seen)
        delta = now - first_seen
        if delta.total_seconds() >= greylist_timeout:
            logger.debug("greylist check: passed, increasing whitelist hit"
                          " counter")
            cursor.execute("""
INSERT OR IGNORE INTO whitelist (client_name, hit_count) VALUES (?, 0);""",
                           (client_name, ))
            cursor.execute("""
UPDATE whitelist SET last_seen = ?, hit_count = hit_count + 1;""",
                           (now,))
            dbconn.commit()
            return PASSED
        cursor.execute("""UPDATE greylist
        SET last_seen = ?
        WHERE sender=? AND recipient=? AND client_name=?""",
                       (now,) + key)
        dbconn.commit()
        logger.debug("greylist check: defer")
        return FAILED

def process_request(attrs):
    dbconn = get_db()
    cursor = dbconn.cursor()

    try:
        sender = attrs["sender"]
        recipient = attrs["recipient"]
        client_name = attrs["client_name"]

        logger.debug("processing request: sender=%r, recipient=%r, client_name=%r",
                      sender, recipient, client_name)
        if _check_whitelist(cursor, client_name):
            return PASSED

        return _check_greylist(dbconn, cursor, sender, recipient, client_name)
    finally:
        cursor.close()

def setup_db(dbconn):
    try:
        verify_db(dbconn)
        logger.info("database schema verified successfully")
    except ValueError as err:
        logger.warn("database schema has errors: %s", err)
        create_db(dbconn)

def verify_db(dbconn):
    cursor = dbconn.execute("SELECT * FROM SQLITE_MASTER")
    try:
        found = set()
        for type_, name, _, _, sql in cursor:
            if sql is None:
                continue
            try:
                if sql != SCHEMA[(type_, name)]:
                    logger.warn("verifying: sql schema differs. found %r", sql)
                    logger.info("verifying: expected %r", SCHEMA[(type_, name)])
                    raise ValueError("Schema differs")
            except KeyError as err:
                raise ValueError("Unexpected {}: {}".format(type_, err))
            found.add(name)
        missing = set(table
                      for (type_, table) in SCHEMA.keys()
                      if type_ == "table") - found
        if missing:
            raise ValueError("Missing tables: {}".format(", ".join(missing)))
    finally:
        cursor.close()

if __name__ == "__main__":
    import argparse
    import configparser
    import logging
    import sys

    parser = argparse.ArgumentParser(
        description="""Accept Postfix policy check requests on stdin and perform
        greylisting. Returns an action code depending on greylisting result. For
        configuration details please see the comments at the start of
        greylist.py"""
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
    logger = logging.getLogger("greylist")

    if args.config is not None:
        load_config(args.config)

    try:
        while True:
            request = read_request(sys.stdin)
            if request is None:
                break

            clean_request(request)
            response = process_request(request)
            if response == PASSED:
                print(response_pass)
            elif response == FAILED:
                print(response_fail)
            else:
                raise AssertionError("Programming error")

            gc_db()
    except KeyboardInterrupt:
        pass

else:
    # defer configuration of logger until the end
    import logging
    logger = logging.getLogger("greylist")
