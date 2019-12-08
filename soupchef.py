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

from time import sleep
from random import randint

import requests
from bs4 import BeautifulSoup, SoupStrainer

from index import open_index

def fetch_daily() -> None:
    '''Fetches the daily recipe from the RSS feed via fetch_urls(). The output will be saved in the output folder.'''
    url = 'https://www.chefkoch.de/recipe-of-the-day/rss'
    
    logger.info('Fetching recipe of the day')
    
    r = requests.get(url)
    
    if r:
        soup = BeautifulSoup(r.text, 'xml')
    else:
        logger.error(f'Could not fetch RSS feed, status code {r.status_code}. Exiting.')
        exit(1)

    item = soup.item
    url = item.link.text
    
    fetch_urls([url])

def fetch_ids(ids: list) -> None:
    '''Fetches a list of IDs after conversion to URLs via fetch_urls().
    
    Parameters
    ----------
    ids: list
        A list of valid IDss.
    '''

    logger.debug(f'\tConverting IDs {ids}')

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
    
    stack = [urls]
    total_fetched = 0

    for level in stack:
        logger.info(f'Fetching {len(level)} URL(s) on recursion step {len(stack)-1} of {args.recursion_depth}')
        logger.debug(level)
        
        new_ids = []
        related_urls = []

        for url in level:
            id = url_to_id(url)
            if args.force_all or id not in index:
                logger.info(f'Fetching {id}')
                data = fetch_url(url)
                if data:
                    total_fetched += 1
                    _write_json(data)
                    related_urls.extend(id_to_url(x) for x in data['related'])
                    index.add(id)
                    new_ids.append(id)
                # rate limiting TODO: user control
                sleep(randint(100, 500)/1000)
            else:
                if len(stack) == 1:
                    # always notify the user when URLs in the first step are being skipped
                    logger.warning(f'Skipping  duplicate {id} on level 0. Use the -f flag to override this behavior.')
                else:
                    logger.debug(f'Skipping duplicate {id}')

        if len(stack) <= args.recursion_depth and len(related_urls) > 0:
            stack.append(related_urls)
    
    logger.info(f'Fetched a total of {total_fetched} recipes.')

def fetch_url(url: str) -> dict:
    '''Fetches all relevant data from a single URL. The number of comments to fetch is determined by the -c command line argument.
    
    Parameters
    ----------
    url: str
        'A valid URL
    '''

    data = {}
    r = requests.get(url)

    if r:
        logger.debug(f'\tFetching {url}')
        soup = BeautifulSoup(r.text, 'lxml')
        id = url_to_id(url)
        comments = _fetch_comments(id)
        data = {
            'id': id,
            'title': _get_title(soup),
            'author': _get_author(soup),
            'images': _get_images(soup),
            'keywords': _get_keywords(soup),
            'category': _get_category(soup),
            'category_breadcrumbs': _get_breadcrumbs(soup),
            'related': _get_related_ids(soup),
            'ingredients': _get_ingredients(soup),
            'text': _get_recipe_text(soup),
            'comment_count': len(comments),
            'comments': comments
        }
    else:
        logger.warning(f'Could not fetch {url} status {r.status_code}')

    return data

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
    
    num_pages = math.ceil(args.num/30)
    logger.debug(f'\tNumber of pages to fetch: {num_pages}')

    urls = []
    for search in search_strings:
        logger.debug(f'\tSearch term: {search}')
        for page in range(num_pages):
            logger.debug(f'\tProcessing page {page+1}')
            results = _fetch_search_page(search, page+1)
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
        The page number of the search results to get.
    '''
    page_number = int(page_number)
    startindex = (page_number - 1) * 30
    url = f'https://www.chefkoch.de/rs/s{startindex}/{search_string}/Rezepte.html'

    strainer = SoupStrainer('script', type="application/ld+json")

    r = requests.get(url)
    soup = BeautifulSoup(r.text, 'lxml', parse_only=strainer)
    json_raw = soup.find('script', text=re.compile(r'.+itemListElement.+')).text
    data = json.loads(json_raw)
    return [x['url'] for x in data['itemListElement']]

def _fetch_comments(id: str, num: int = -1) -> list:
    '''Gets comments via the undocumented official JSON-API and returns them as a list of comment objects
    with the structure
        Comment:
            text:   str
            author: str
    '''
    
    if num < 0:
        num = args.comment_num
    
    if num > 0:
        api_comments_url = f'https://api.chefkoch.de/v2/recipes/{id}/comments?offset=0&limit={num}&order=1&orderBy=1'
    else:
        api_comments_url = f'https://api.chefkoch.de/v2/recipes/{id}/comments?offset=0&order=1&orderBy=1'
    

    r = requests.get(api_comments_url)

    comments = []
    if r:
        comments_raw = r.json()

        for elem in comments_raw['results']:
            text = elem['text']
            author = elem['owner']['username']
            comments.append({
                'text': text,
                'author': author
            })
        logger.debug(f'\tFetched {len(comments)} comments')
    else:
        logger.warning('Could not fetch comments')
    
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
    logger.debug(f'\tTitle: {title}')

    return title

def _get_author(soup: BeautifulSoup) -> str:
    '''Extracts the author name from JSON data embedded in the page and returns it as a string.'''

    json_raw = soup.find(lambda tag:tag.name=='script' and 'author' in tag.text, type='application/ld+json', )
    json_data = json.loads(json_raw.text)
    return json_data['author']['name']

def _get_keywords(soup: BeautifulSoup) -> list:
    ''''Extracts the recipe keywords from JSON data embedded in the page and returns them as a list of strings.'''
    
    json_raw = soup.find(lambda tag:tag.name=='script' and 'keywords' in tag.text, type='application/ld+json', )
    json_data = json.loads(json_raw.text)
    return json_data['keywords']

def _get_category(soup: BeautifulSoup) -> str:
    ''''Extracts the recipe category from JSON data embedded in the page and returns it as a string.'''

    json_raw = soup.find(lambda tag:tag.name=='script' and 'recipeCategory' in tag.text, type='application/ld+json', )
    json_data = json.loads(json_raw.text)
    return json_data['recipeCategory']

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

    related_h = soup.find('h2', text=re.compile(r'^Weitere Rezepte.*'))
    related_div = related_h.find_next_sibling('div')
    related_links = related_div.find_all('a')
    related_ids = [url_to_id(x['href']) for x in related_links]
    
    return related_ids

def _get_images(soup: BeautifulSoup) -> list:
    '''Extracts the recipe images from the page and returns them as a list of URLs'''

    images = soup.find_all('amp-img', src=re.compile(r'.+rezepte.+bilder.+960x640.+'))
    return [x['src'] for x in images]

def _write_json(data: dict, filename: str = None) -> None:
    '''Writes a capture data structure to a json file in the output folder path set in outfolder.'''
    
    if not filename:
        filename = data['id'] + '.json'

    outfolder = os.path.expanduser(args.outfolder)
    filepath = outfolder + '/' + filename

    if not os.path.exists(outfolder):
        os.makedirs(outfolder)

    with open(filepath, mode='w', encoding='utf-8') as outfile:
        json.dump(data, outfile, ensure_ascii=False, indent=2)

def main():
    ### command line argument parsing

    argparser = argparse.ArgumentParser(description='Fetches recipes and their metadata from a big German cooking portal.')

    # mutually exclusive main modes

    mode_group = argparser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument('-d', '--daily', action='store_true',
        help='Downloads the recipe of the day, no further input required. Can be combined with -c and -r.')
    mode_group.add_argument('-s', '--search', action='store_true',
        help='Searches for the entered term and fetches the results. Multiple searches need to be separated by spaces. Can be combined with -n, -c and -r.')
    mode_group.add_argument('-u', '--url', action='store_true',
        help='Fetches the entered URLs. Can be combined with -c and -r.')
    mode_group.add_argument('-i', '--id', action='store_true',
        help='Fetches the entered IDs. Can be combined with -c and -r.')
    
    # setting flags

    argparser.add_argument('-f', action='store_true', dest='force_all',
        help="Force fetch all elements, don't skip already existing.")
    
    argparser.add_argument('-o', default='crawl', dest='outfolder',
        help='Sets the output folder.')

    argparser.add_argument('-n', default=30, type=int, dest='num',
        help='Sets the number of elements to fetch. For search multiples of 30 are sensible values.')

    argparser.add_argument('-r', default=0, type=int, dest='recursion_depth',
        help='''Sets the number of recursion steps to take. Recursion works breadth-first on recommended recipes,
        i.e. the initial list of recipes will be fetched, then their recommended recipes, then the recommended recipes of the recommended recipes, etc.''')

    argparser.add_argument('-c', default=100, type=int, dest='comment_num',
        help='Sets the number of comments to load per recipe.')

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

if __name__ == "__main__":
    main()