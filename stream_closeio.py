#!/usr/bin/env python3

import json
import logging
import os
import sys
import argparse

import requests
import stitchstream as ss
import backoff

logger = logging.getLogger()

base_url = 'https://app.close.io/api/v1'

return_limit = 100
default_start_date = '2000-01-01T00:00:00Z'

session = requests.Session()

state = {
    'leads': default_start_date
}

class StitchException(Exception):
    def __init__(self, message):
        self.message = message

def configure_logging(level=logging.DEBUG):
    global logger
    logger.setLevel(level)
    ch = logging.StreamHandler()
    ch.setLevel(level)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

def client_error(e):
    return e.response is not None and 400 <= e.response.status_code < 500

@backoff.on_exception(backoff.expo,
                      (requests.exceptions.RequestException),
                      max_tries=5,
                      giveup=client_error,
                      factor=2)
def request(**kwargs):
    if 'method' not in kwargs:
        kwargs['method'] = 'get'

    response = session.request(**kwargs)
    response.raise_for_status()
    return response

def get_leads(auth, query_date, offset=0):
    global state

    params = {
        '_limit': return_limit,
        '_skip': offset,
        'query': 'date_updated >= ' + query_date + ' sort:date_updated'
    }
    logger.info("Fetching leads starting at " + query_date + "; offset " + str(offset) + "; limit " + str(return_limit));
    response = request(url=base_url + '/lead/', params=params, auth=auth)

    body = response.json()
    data = body['data']
    if len(data) == 0:
        return
    
    ss.write_records('leads', data)
    state['leads'] = data[-1]['date_updated']
    ss.write_bookmark(state)
    
    if 'has_more' in body and body['has_more']:
        get_leads(auth, query_date, offset = offset + return_limit)

def do_check(args):
    with open(args.config) as file:
        config = json.load(file)

    auth = (config['api_key'],'')

    params = {
        '_limit': 10
    }

    try:
        request(url=base_url + '/lead/', params=params, auth=auth)
    except requests.exceptions.RequestException as e:
        logger.fatal("Error checking connection using " + e.request.url +
                     "; received status " + str(e.response.status_code) +
                     ": " + e.response.text)
        sys.exit(-1)

def do_sync(args):
    global state
    with open(args.config) as file:
        config = json.load(file)

    if args.state != None:
        with open(args.state) as file:
            state = json.load(file)

    logger.info('Replicating all Close.io data')

    ## TODO: write schemas to stream

    auth = (config['api_key'],'')
    
    try:
        get_leads(auth, state['leads'])
    except requests.exceptions.RequestException as e:
        logger.fatal("Error on " + e.request.url +
                     "; received status " + str(e.response.status_code) +
                     ": " + e.response.text)
        sys.exit(-1)
    
def main():
    parser = argparse.ArgumentParser()

    subparsers = parser.add_subparsers()
    
    parser_check = subparsers.add_parser('check')
    parser_check.set_defaults(func=do_check)

    parser_sync = subparsers.add_parser('sync')
    parser_sync.set_defaults(func=do_sync)

    for subparser in [parser_check, parser_sync]:
        subparser.add_argument('-c', '--config', help='Config file', required=True)    
        subparser.add_argument('-s', '--state', help='State file')
    
    args = parser.parse_args()
    configure_logging()

    if 'func' in args:
        args.func(args)
    else:
        parser.print_help()
        exit(1)


if __name__ == '__main__':
    main()
