#!/usr/bin/env python3

import argparse
import os
import json

import requests
from bs4 import BeautifulSoup

def fetch_daily(args):
    pass

def main():
    argparser = argparse.ArgumentParser(description='Fetches recipes and their metadata from chefkoch.de')

    mode_group = argparser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument('-d', '--daily', action='store_true',
        help='Downloads the recipes of the day, no further input required.')
    mode_group.add_argument('-s', '--search', action='store_true',
        help='Searches for the entered term and fetches the results. Can be combined with -n and -r.')
    mode_group.add_argument('-l', '--link', action='store_true',
        help='Fetches the entered URLs. Can be combined with and -r.')
    
    argparser.add_argument('-o', default='soupchef', dest='outfolder',
        help='output folder')

    argparser.add_argument('-n', default=10, dest='num',
        help='number of elements to fetch')

    argparser.add_argument('-r', default=0 , dest='rdepth',
        help='number of recursion steps')

    argparser.add_argument('input', nargs='*',
        help='input arguments')

    args = argparser.parse_args()

    if args.daily:
        fetch_daily(args)
    elif args.search:
        print("Not yet implemented.")
    elif args.link:
        print("Not yet implemented.")

if __name__ == "__main__":
    main()