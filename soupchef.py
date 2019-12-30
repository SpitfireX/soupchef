#!/usr/bin/env python3

'''This is the main module of soupchef, a webcrawler/data extractor for a big german cooking portal.
The main intention behint soupchef is to provide a flexible command line utility for diverse crawling tasks.'''

import argparse
import os
import json
import datetime
import re
import math
import logging
import datetime
import concurrent.futures
import signal

from time import sleep
from random import randint

import requests
from bs4 import BeautifulSoup, SoupStrainer

from index import open_index
from random_http_headers import random_headers

# sort modes
_search_sort_modes = {
    'relevance': '',
    'daily': 'o1',
    'date': 'o3',
    'preptime': 'o4',
    'difficulty': 'o5',
    'rating': 'o8'
}

# file naming modes
_filename_modes = [
    'plain',
    'title'
]

# directory naming modes
_dirname_modes = [
    'flat',
    'category',
    'date'
]

# global variable that keeps track of the time of the last HTTP request
_last_request_time = datetime.datetime.now()

# global flag set after the program received a shutdown signal
_shutdown = False

def _wait_time() -> int:
    '''Returns the rate limit set with the -l flag. The flag accepts either a single constant value or a range
    that is used for randomization. The flag value must be given in seconds. This function returns a value in
    microseconds.'''
    
    frags = args.rate_limit.split('-')

    if len(frags) == 1:
        try:
            limit = float(frags[0])
        except:
            logger.critical('Specified rate limit is not a decimal number.')
            exit(1)

        if limit < 0:
            logger.critical('Specified rate limit must not be negative.')
            exit(1)
    elif len(frags) == 2:
        try:
            lower = float(frags[0])
            upper = float(frags[1])
        except:
            logger.critical('Specified rate limit range is not in format "decimalnumber-decimalnumber".')
            exit(1)

        if lower < 0 or upper < 0:
            logger.critical('Specified rate limit must not be negative.')
            exit(1)

        limit = randint(lower*1000, upper*1000) / 1000
    else:
        logger.critical('Specified rate limit range is not in format "decimalnumber-decimalnumber".')
        exit(1)
    
    return limit * 1000000

def _wait_rate_limit() -> None:
    '''Blocks until the set rate limit allows a new HTTP request.'''

    global _last_request_time

    rate_limit = _wait_time()
    time_diff = (datetime.datetime.now() - _last_request_time).microseconds
    
    if time_diff < rate_limit:
        sleep_time = (rate_limit - time_diff) / 1000000
        # logger.debug(f'HTTP Rate Limit: sleeping for {sleep_time} seconds.')
        sleep(sleep_time)
    
    _last_request_time = datetime.datetime.now()

def fetch_daily() -> None:
    '''Fetches the daily recipe from the RSS feed via fetch_urls(). The output will be saved in the output folder.'''
    url = 'https://www.chefkoch.de/recipe-of-the-day/rss'
    
    logger.info('Fetching recipe of the day')
    
    r = requests.get(url, headers=random_headers())
    
    if r:
        soup = BeautifulSoup(r.text, 'xml')
    else:
        logger.error(f'Could not fetch RSS feed, status code {r.status_code}. Exiting.')
        exit(1)

    item = soup.item
    url = item.link.text
    
    fetch_urls([url])

def fetch_random() -> None:
    '''Fetches a number of random recipes via fetch_urls(). The number of recipes to fetch is determined by the -n flag.
    The output will be saved in the output folder.'''
    
    logger.info(f'Fetching {args.num} random recipe(s)')

    url = 'https://www.chefkoch.de/rezepte/zufallsrezept/'
    random_urls = []
    
    while len(random_urls) < args.num:
        _wait_rate_limit()
        r = requests.get(url, allow_redirects=False, headers=random_headers())

        if r:
            random_url = 'https://chefkoch.de' + r.headers['Location']
            random_urls.append(random_url)
            logger.debug(f'\tGot random URL: {random_url}')
    
    fetch_urls(random_urls)

def fetch_ids(ids: list) -> None:
    '''Fetches a list of IDs after conversion to URLs via fetch_urls().
    
    Parameters
    ----------
    ids: list
        A list of valid IDss.
    '''

    urls = [id_to_url(id) for id in ids]
    fetch_urls(urls)

def fetch_urls(urls: list) -> None:
    '''Fetches a list of URLs via fetch_url(). The number of recursion steps to take is determined by the -r command line argument.
    The output will be saved in the output folder.

    When using recursion the crawler works breadth first. On each step all URLs will be fetched and their related recipe URLs
    provide the next recursion step.
    
    Parameters
    ----------
    urls: list
        A list of valid URLs.
    '''
    
    if args.index_only:
        logger.debug('Adding IDs to index (index-only flag set, not fetching).')
        for url in urls:
            index.add(url_to_id(url))
        return

    stack = [urls]
    total_fetched = 0

    for level in stack:
        logger.info(f'Fetching {len(level)} URL(s) on recursion step {len(stack)-1} of {args.recursion_depth}')
        logger.debug(level)
        
        new_ids = []
        related_urls = []
        workers = {}

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            for url in level:
                id = url_to_id(url)
                if args.force_all or id not in index:
                    _wait_rate_limit()
                    logger.debug(f'Starting fetch {id}')
                    workers[id] = executor.submit(fetch_and_save_url, url)
                else:
                    if len(stack) == 1:
                        # always notify the user when URLs in the first step are being skipped
                        logger.warning(f'Skipping  duplicate {id} on level 0. Use the -f flag to override this behavior.')
                    else:
                        logger.debug(f'Skipping duplicate {id}')

        for id, worker in workers.items():
            data = worker.result()
            if data:
                total_fetched += 1
                related_urls.extend(id_to_url(x) for x in data['related'])
                new_ids.append(id)

        if len(stack) <= args.recursion_depth and len(related_urls) > 0:
            stack.append(related_urls)
    
    logger.info(f'Fetched a total of {total_fetched} recipes.')

def fetch_and_save_url(url: str) -> dict:
    '''Fetches all relevant data from a single URL, adds it to the index and saves it to the disk. The number of comments to fetch is determined by the -c command line argument.
    
    Parameters
    ----------
    url: str
        'A valid URL
    '''
    data = fetch_url(url)
    
    if data and not _shutdown:
        index.add(data['id'])
    
    if not _shutdown:
        _write_json(data)
    
    return data

def fetch_url(url: str) -> dict:
    '''Fetches all relevant data from a single URL. The number of comments to fetch is determined by the -c command line argument.
    
    Parameters
    ----------
    url: str
        'A valid URL
    '''
    logger.debug(f'\tFetching {url}')
    data = {}

    for i in range(10):
        r = requests.get(url, headers=random_headers())
        if not r.ok:
            logger.warning(f'HTTP error code {r.status_code} for url {url} on try #{i}.')
        else:
            break

    if not r.ok:
        logger.warning(f'Could not fetch {url} status {r.status_code}')
    else:
        soup = BeautifulSoup(r.text, 'lxml')
        id = url_to_id(url)
        try:
            data = {
                'id': id,
                'url': url,
                'title': _get_title(soup),
                'author': _get_author(soup),
                'date': _get_date(soup),
                'rating': _get_rating(soup),
                'images': _get_images(soup),
                'keywords': _get_keywords(soup),
                'category': _get_category(soup),
                'category_breadcrumbs': _get_breadcrumbs(soup),
                'related': _get_related_ids(soup),
                'ingredients': _get_ingredients(soup),
                'text': _get_recipe_text(soup)
            }
        except Exception as e:
            logger.warning(f'Received malformed HTML data for url {url}.')
            logger.debug(str(e))
            return data

        comments = fetch_comments(id)
        data['comment_count'] = len(comments)
        data['comments'] =comments

    logger.info(f'Fetched {data["id"]} - {data["title"]} - {data["comment_count"]} comments')

    return data

def fetch_all() -> None:
    '''Fetches all recipes. To get a list of all recipes a modified search is used. For that the regular search results are being used, but with an empty search argument.'''

    if args.num == -1:
        total = _get_total_recipe_count()
    else:
        total = args.num
    total_pages = math.ceil(total/30)
    logger.info(f'Fetching all recipes with sort Mode "{args.search_sort_mode}":')
    logger.info(f'\t{total} recipes on {total_pages} pages.')
    

    args.recursion_depth = 0
    
    fetch = True
    fetched = 0
    page = args.page
    while fetch:
        logger.info(f'Fetching page: {page} of {total_pages}')
        _wait_rate_limit()
        urls = _fetch_search_page('', page)

        if len(urls) > 0:
            if fetched + len(urls) <= args.num:
                fetch_urls(urls)
                fetched += len(urls)
            else:
                end = args.num - fetched
                fetch_urls(urls[:end])
                fetched += len(urls[:end])
                fetch = False
            page += 1
        else:
            fetch = False

    logger.info(f'Fetched a total of {fetched} recipes on {page} pages.')

def fetch_again() -> None:
    '''Fetches all recipes in the index again.'''

    logger.info('Refreshing all recipes in the index.')

    args.recursion_depth = 0
    args.force_all = True
    args.index_only = False

    fetch_ids(index)

def fetch_search(search_strings: list) -> None:
    '''Fetches a list of search strings via _fetch_search_page() and fetch_urls(). The number of recipes to fetch per search string is 
    defined by the -n command line argument. The output will be saved in the output folder.
    
    Parameters
    ----------
    search_strings: list
        A list of search terms. Search terms may contain multiple words.
    '''

    logger.info(f'Fetching search terms: {search_strings}')
    search_strings = [re.sub(r'\s', '+', string.strip()) for string in search_strings]
    
    logger.info(f'\tSort Mode: {args.search_sort_mode}')

    num_pages = math.ceil(args.num/30)
    start_page = args.page
    logger.debug(f'\tNumber of pages to fetch: {num_pages}')

    urls = []
    for search in search_strings:
        logger.debug(f'\tSearch term: {search}')
        for page in range(start_page, start_page+num_pages+1):
            logger.debug(f'\tProcessing page {page}')
            _wait_rate_limit()
            results = _fetch_search_page(search, page)
            logger.debug(f'\tReceived {len(results)} results')
            urls.extend(results)
            if len(results) < 30:
                break
    
    urls = urls[:args.num]
    
    logger.info(f'Fetched {len(urls)} search results total')

    fetch_urls(urls)

def _fetch_search_page(search_string: str, page_number: int) -> list:
    '''Fetches a single search result page and returns all recipe URLs as a list
    
    Parameters
    ----------
    search_string: str
        The string to be searched. May not contain whitespace, instead, words ar separated by +.
    page_number: int
        The page number of the search results to get. 1 is the first page.
    '''

    page_number = int(page_number)
    startindex = (page_number - 1) * 30
    sort_mode = _search_sort_modes[args.search_sort_mode]
    url = f'https://www.chefkoch.de/rs/s{startindex}{sort_mode}/{search_string}/Rezepte.html'

    strainer = SoupStrainer('script', type="application/ld+json")

    for i in range(10):
        _wait_rate_limit()
        r = requests.get(url, headers=random_headers())
        if not r.ok:
            logger.warning(f'HTTP error code {r.status_code} for search page {page_number} on try #{i}.')
        else:
            break
    
    result = []

    if r.ok:
        soup = BeautifulSoup(r.text, 'lxml', parse_only=strainer)
        try:
            json_raw = soup.find('script', text=re.compile(r'.+itemListElement.+')).text
            data = json.loads(json_raw, strict=False)
            result = [x['url'] for x in data['itemListElement']]
        except Exception as e:
            logger.error(f'Malformed HTML for search page {page_number}, written to file.')
            with open('crash_raw.html', mode='w') as rawf, open('crash_soup.html', mode='w') as soupf:
                rawf.write(json_raw)
                soupf.write(soup.prettify())
    else:
        logger.error(f'Could not fetch search page {page_number}.')
    
    return result

def fetch_comments(id: str, num: int = None) -> list:
    '''Gets comments via the undocumented official JSON-API and returns them as a list of comment objects
    with the structure
        Comment:
            text:   str
            author: str
    '''
    
    if num is None:
        num = args.comment_num

    if num > 0:
        api_comments_url = f'https://api.chefkoch.de/v2/recipes/{id}/comments?limit={num}&order=1&orderBy=1'
    elif num < 0:
        api_comments_url = f'https://api.chefkoch.de/v2/recipes/{id}/comments?order=1&orderBy=1'
    else:
        return []
    
    json_pages = []
    comments = []
    offset = 0
    total_count = 0

    while True:
        for i in range(10):
            custom_headers = random_headers()
            # override default since a regular browser would only accept JSON from a JSON URL
            custom_headers['accept'] = 'application/json'
            url = api_comments_url + f'&offset={offset}'
            _wait_rate_limit()
            r = requests.get(url, headers=custom_headers)

            if not r.ok:
                logger.warning(f'HTTP error code {r.status_code} for comments for {id} at offset {offset} on try #{i}.')
            else:
                break
        
        if not r.ok:
            logger.warning(f'Could not fetch comments for {id} at offset {offset}.')
        else:
            try:
                json_data = json.loads(r.text, strict=False)
                json_pages.append(json_data)
            except Exception as e:
                logger.error(f'Did not receive JSON data for comments for {id} at offset {offset}.')

        total_count = json_data['count']

        if offset + 500 >= total_count:
            break
        else:
            offset += 500

    if not json_pages:
        logger.error(f'Could not fetch comments for {id}.')
    else:
        for json_page in json_pages:
            try:
                for elem in json_page['results']:
                    text = elem['text']
                    owner = elem['owner']
                    if owner:
                        author = owner['username']
                    else:
                        author = None
                    date = elem['createdAt']
                    comments.append({
                        'text': text,
                        'author': author,
                        'date': date
                    })
            except Exception as e:
                logger.warning(f'Received malformed JSON data for comments {id}.')
                logger.debug(str(e))
    
    return comments

def url_to_id(url: str) -> str:
    '''Converts an URL into a valid ID
    
    Parameters
    ----------
    url: str
        A valid URL
    '''

    return re.search(r'rezepte/(\d+)/', url)[1]

def id_to_url(id: str) -> str:
    '''Converts an ID into a valid URL
    
    Parameters
    ----------
    id: str
        A valid ID
    '''

    return f'https://chefkoch.de/rezepte/{id}/'

def _get_title(soup: BeautifulSoup) -> str:
    '''Extracts the title of the recipe from the page and returns it as a string.'''
    
    title = soup.h1.text.strip()

    return title

def _get_author(soup: BeautifulSoup) -> str:
    '''Extracts the author name from JSON data embedded in the page and returns it as a string.'''

    json_raw = soup.find(lambda tag:tag.name=='script' and 'author' in tag.text, type='application/ld+json', )
    json_data = json.loads(json_raw.text)
    return json_data['author']['name']

def _get_keywords(soup: BeautifulSoup) -> list:
    '''Extracts the recipe keywords from JSON data embedded in the page and returns them as a list of strings.'''
    
    json_raw = soup.find(lambda tag:tag.name=='script' and 'keywords' in tag.text, type='application/ld+json', )
    keywords = []
    
    if json_raw:
        json_data = json.loads(json_raw.text)
        keywords = json_data['keywords']
    
    return keywords

def _get_category(soup: BeautifulSoup) -> str:
    '''Extracts the recipe category from JSON data embedded in the page and returns it as a string.'''

    json_raw = soup.find(lambda tag:tag.name=='script' and 'recipeCategory' in tag.text, type='application/ld+json', )
    json_data = json.loads(json_raw.text)
    return json_data['recipeCategory']

def _get_rating(soup: BeautifulSoup) -> dict:
    '''Extracts the recipe rating and review count from JSON data embedded in the page and returns it as a dict.'''

    json_raw = soup.find(lambda tag:tag.name=='script' and 'aggregateRating' in tag.text, type='application/ld+json', )
    
    rating = {}
    if json_raw:
        json_data = json.loads(json_raw.text)
        rating_data = json_data['aggregateRating']
        rating = {
            'value': rating_data['ratingValue'],
            'count': rating_data['reviewCount']
            }
    
    return rating

def _get_date(soup: BeautifulSoup) -> str:
    '''Extracts the publishing date of the recipe from JSON data embedded in the page and returns it as a dict.'''
    
    json_raw = soup.find(lambda tag:tag.name=='script' and 'aggregateRating' in tag.text, type='application/ld+json', )
    
    date = None
    if json_raw:
        json_data = json.loads(json_raw.text)
        date = json_data['datePublished']
    
    return date

def _get_breadcrumbs(soup: BeautifulSoup) -> list:
    '''Extracts the category/navigation breadcrumbs from the page and returns them as a list of strings'''

    breadcrumbs_raw = soup.find('div', class_='ds-container').ol.text.strip()
    breadcrumbs = breadcrumbs_raw.split('\ue409') # magic icon font symbol, might break
    breadcrumbs = [x.strip() for x in breadcrumbs[1:]]
    return breadcrumbs

def _get_ingredients(soup: BeautifulSoup) -> list:
    '''Extracts the list of ingredients from the page and returns it as a list of ingredient objects
    with the structure
        Ingredient:
            name:   str
            amount: str
    '''

    heading = soup.find('h2', text='Zutaten')
    parent = heading.parent
    # find all table rows from the surrounding object, there can be multiple tables
    rows = parent.find_all('tr')

    ingredients = []

    # find all the relevant td tags in the rows, there should be two data cells in each row
    # the first one with the amount of the ingredient and the second one with its name
    for row in rows:
        data = row.find_all('td')
        if len(data) > 0:
            name = (data[1].text.strip())
            amount = ' '.join(data[0].text.strip().split())
            amount = None if not amount else amount
            if name:
                ingredients.append({'name':name, 'amount':amount})
    
    return ingredients

def _get_recipe_text(soup: BeautifulSoup) -> str:
    '''Extracts the recipe text from the page and returns it as a string.'''

    heading = soup.find('h2', text='Zubereitung')
    div = heading.find_next_sibling('div')

    return div.text.strip()

def _get_related_ids(soup: BeautifulSoup) -> list:
    '''Extracts the IDs of the related/recommended recipes from the page and returs them as a list of IDs'''
    related_ids = []
    try:
        related_h = soup.find('h2', text=re.compile(r'^Weitere Rezepte.*'))
        related_div = related_h.find_next_sibling('div')
        related_links = related_div.find_all('a')
        related_ids = [url_to_id(x['href']) for x in related_links]
    except:
        logger.debug('\tNo related recipes found.')
    
    return related_ids

def _get_images(soup: BeautifulSoup) -> list:
    '''Extracts the recipe images from the page and returns them as a list of URLs'''

    images = soup.find_all('amp-img', src=re.compile(r'.+rezepte.+bilder.+960x640.+'))
    return [x['src'] for x in images]

def _get_total_recipe_count() -> int:
    '''Finds the current total number of recipes on the website'''
    
    url = 'https://www.chefkoch.de/rs/s0/Rezepte.html'
    strainer = SoupStrainer('h1')

    r = requests.get(url, headers=random_headers())
    soup = BeautifulSoup(r.text, 'lxml', parse_only=strainer)

    return int(soup.h1.span.text.strip().split(' ')[0].replace('.', ''))

def _write_json(data: dict, filename: str = None) -> None:
    '''Writes a capture data structure to a json file in the output folder path set in outfolder.'''
    
    if not filename:
        title = data["title"]
        title = title.replace(' - ', '-')
        title = re.sub(r'\s', '_', title)
        title = re.sub(r'_+', '_', title)
        title = re.sub(r'[^\w\-_]', '', title)
        filename = f'{data["id"]}_{title}.json'
        if args.filename_mode == 'plain':
            filename = data['id'] + '.json'

    subdirs = ''
    if args.dirname_mode == 'category':
        categories = data['category_breadcrumbs'][3:]
        categories = [re.sub(r'[^\w]', '-', s) for s in categories]
        categories = [re.sub(r'-+', '-', s) for s in categories]
        subdirs = '/'.join(categories)
    elif args.dirname_mode == 'date':
        subdirs = data['date'].replace('-', '/')

    outfolder = os.path.expanduser(args.outfolder) + '/' + subdirs + '/'
    filepath = outfolder + '/'  + filename

    if not os.path.exists(outfolder):
        os.makedirs(outfolder, exist_ok=True)

    with open(filepath, mode='w', encoding='utf-8') as outfile:
        json.dump(data, outfile, ensure_ascii=False, indent=2)

def _sigint_handler(self, sig, frame):
    '''Handler to catch SIGINT (Ctrl+C). In case of SIGINT this handler sets the shutdown flag.'''
    _shutdown = True

def main():
    ### install signal handlers
    signal.signal(signal.SIGINT, _sigint_handler)

    ### command line argument parsing

    argparser = argparse.ArgumentParser(description='Fetches recipes and their metadata from a big German cooking portal.')

    # mutually exclusive main modes

    mode_group = argparser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument('-d', '--daily', action='store_true',
        help='Downloads the recipe of the day, no further input required. Can be combined with -c and -r.')
    mode_group.add_argument('-s', '--search', action='store_true',
        help='Searches for the entered term and fetches the results. Multiple searches need to be separated by spaces. Can be combined with -n, -c, -r and -p.')
    mode_group.add_argument('-u', '--url', action='store_true',
        help='Fetches the entered URLs. Can be combined with -c and -r.')
    mode_group.add_argument('-i', '--id', action='store_true',
        help='Fetches the entered IDs. Can be combined with -c and -r.')
    mode_group.add_argument('-z', '--random', action='store_true',
        help='Fetches a number of random recipes. Can be combined with -n, -c and -r.')
    mode_group.add_argument('-a', '--all', action='store_true',
        help='Fetches all recipes. Can be combined with -c and -p.')
    mode_group.add_argument('--refresh', action='store_true',
        help='Fetches all recipes in the index again. Can be combined with -c.')
    
    # setting flags

    argparser.add_argument('-f', action='store_true', dest='force_all',
        help="Force fetch all elements, don't skip already existing.")
    
    argparser.add_argument('-o', default='crawl', dest='outfolder',
        help='Sets the output folder.')

    argparser.add_argument('-n', default=-1, type=int, dest='num',
        help='Sets the number of elements to fetch. For search and all multiples of 30 are sensible values. -1 = all.')

    argparser.add_argument('-r', default=0, type=int, dest='recursion_depth',
        help='''Sets the number of recursion steps to take. Recursion works breadth-first on recommended recipes,
        i.e. the initial list of recipes will be fetched, then their recommended recipes, then the recommended recipes of the recommended recipes, etc.''')

    argparser.add_argument('-c', default=-1, type=int, dest='comment_num',
        help='Sets the number of comments to load per recipe. -1 = all.')
    
    argparser.add_argument('-l', default='0.1-0.5', type=str, dest='rate_limit',
        help='Sets the rate limit for HTTP(S) requests in seconds. The value must either be a single constant (e.g. "0.8") or a range (e.g. "0.25-4") that is used for randomization.')

    argparser.add_argument('-p', default=1, type=int, dest='page',
        help='Sets the number of the first page to fetch.')

    argparser.add_argument('--sort', default='relevance', choices=_search_sort_modes.keys(), type=str, dest='search_sort_mode',
        help='Sets the sort mode for the search results.')
    
    argparser.add_argument('--filenames', default='title', choices=_filename_modes, type=str, dest='filename_mode',
        help='Sets the format for the output file names. Plain: recipe ID. Title: recipe ID and recipe title.')
    
    argparser.add_argument('--dirnames', default='flat', choices=_dirname_modes, type=str, dest='dirname_mode',
        help='Sets the format of the output directory structure. Flat: all files in the base directory. Category: grouped into subdirectories based on the recipe category. Date: grouped into subdirectories based on the creation date.')

    argparser.add_argument('--index-only', action='store_true', dest='index_only',
        help="Don't fetch anything and only add the IDs of all operations to the index. This is useful to build a list of IDs for later consumption.")

    # verbosity flags

    argparser.add_argument('-q', action='store_true', dest='quiet',
        help='Suppress any console output')

    argparser.add_argument('-v', action='store_const', const=logging.INFO, dest='verbosity', default=logging.WARNING,
        help='Show informative console output.')
    
    argparser.add_argument('-vv', action='store_const', const=logging.DEBUG, dest='verbosity',
        help='Show debug console output.')

    # blanket input
    argparser.add_argument('input', nargs='*',
        help='input arguments')

    global args
    args = argparser.parse_args()

    ### logging setup

    global logger
    logger = logging.getLogger('soupchef')
    logger.setLevel(args.verbosity)

    formatter = logging.Formatter('[%(name)-14s][%(levelname)-8s]: %(message)s')

    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    
    if not args.quiet: 
        logger.addHandler(ch)

    ### index setup

    global index
    index = open_index(args.outfolder + '/index.dat')

    ### main mode selection

    if args.daily:
        fetch_daily()
    elif args.search:
        fetch_search(args.input)
    elif args.url:
        fetch_urls(args.input)
    elif args.id:
        fetch_ids(args.input)
    elif args.random:
        fetch_random()
    elif args.all:
        fetch_all()
    elif args.refresh:
        fetch_again()

if __name__ == "__main__":
    main()
