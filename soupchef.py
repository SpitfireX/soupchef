#!/usr/bin/env python3

import argparse
import os
import json
import datetime
import re

import requests
from bs4 import BeautifulSoup

def fetch_daily():
    url = 'https://www.chefkoch.de/recipe-of-the-day/rss'
    r = requests.get(url)
    soup = BeautifulSoup(r.text, 'xml')

    item = soup.item
    url = item.link.text
    
    fetch_urls([url])

def fetch_ids(ids):
    urls = [get_url(id) for id in ids]
    fetch_urls(urls)

def fetch_urls(urls):
    index_path = args.outfolder + '/index.dat'
    try:
        with open(index_path, mode='r', encoding='utf-8-sig') as infile:
            index = [line.strip() for line in infile]
    except FileNotFoundError:
        index = []

    new_ids = []

    for url in urls:
        id = get_id(url)
        if id not in index:
            data = fetch_url(url)
            write_json(data)
            index.append(id)
            new_ids.append(id)

    with open(index_path, mode='a', encoding='utf-8') as outfile:
        outfile.writelines(line + '\n' for line in new_ids)


def fetch_url(url):
    r = requests.get(url)
    if r:
        soup = BeautifulSoup(r.text, 'lxml')
        id = get_id(url)
        comments = fetch_comments(id)
        data = {
            'id': id,
            'title': get_title(soup),
            'author': get_author(soup),
            'keywords': get_keywords(soup),
            'category': get_category(soup),
            'category_breadcrumbs': get_breadcrumbs(soup),
            'related': get_related_ids(soup),
            'ingredients': get_ingredients(soup),
            'text': get_text(soup),
            'comment_count': len(comments),
            'comments': comments
        }

    return data

def get_id(url):
    return re.search(r'rezepte/(\d+)/', url)[1]

def get_url(id):
    return f'https://chefkoch.de/rezepte/{id}/'

def get_title(soup):
    return soup.h1.text.strip()

def get_author(soup):
    return soup.find('a', {'class': 'bi-profile'}).text.strip().split(' ')[-1]

def get_keywords(soup):
    json_raw = soup.find(lambda tag:tag.name=='script' and 'keywords' in tag.text, type='application/ld+json', )
    json_data = json.loads(json_raw.text)
    return json_data['keywords']

def get_category(soup):
    json_raw = soup.find(lambda tag:tag.name=='script' and 'recipeCategory' in tag.text, type='application/ld+json', )
    json_data = json.loads(json_raw.text)
    return json_data['recipeCategory']

def get_breadcrumbs(soup):
    breadcrumbs_raw = soup.find('div', class_='ds-container').ol.text.strip()
    breadcrumbs = breadcrumbs_raw.split('\ue409')
    breadcrumbs = [x.strip() for x in breadcrumbs[1:]]
    return breadcrumbs

def get_ingredients(soup):
    heading = soup.find('h2', text='Zutaten')
    parent = heading.parent
    rows = parent.find_all('tr')

    ingredients = []

    for row in rows:
        data = row.find_all('td')
        if len(data) > 0:
            name = (data[1].text.strip())
            amount = ' '.join(data[0].text.strip().split())
            if name:
                ingredients.append({'name':name, 'amount':amount})
    
    return ingredients

def get_text(soup):
    heading = soup.find('h2', text='Zubereitung')
    div = heading.find_next_sibling('div')

    return div.text.strip()

def get_related_ids(soup):
    related_h = soup.find('h2', text=re.compile(r'^Weitere Rezepte.*'))
    related_div = related_h.find_next_sibling('div')
    related_links = related_div.find_all('a')
    related_ids = [get_id(x['href']) for x in related_links]
    
    return related_ids

def fetch_comments(id, num=-1):
    if num < 0:
        num = args.comment_num
    
    if num > 0:
        api_comments_url = f'https://api.chefkoch.de/v2/recipes/{id}/comments?offset=0&limit={num}&order=1&orderBy=1'
    else:
        api_comments_url = f'https://api.chefkoch.de/v2/recipes/{id}/comments?offset=0&order=1&orderBy=1'
    
    comments_raw = requests.get(api_comments_url).json()
    
    comments = []
    for elem in comments_raw['results']:
        text = elem['text']
        author = elem['owner']['username']
        comments.append({
            'text': text,
            'author': author
        })
    
    return comments

def write_json(data, filename=None):
    if not filename:
        filename = data['id'] + '.json'

    outfolder = os.path.expanduser(args.outfolder)
    filepath = outfolder + '/' + filename

    if not os.path.isdir(outfolder):
        os.mkdir(outfolder)

    with open(filepath, mode='w', encoding='utf-8') as outfile:
        json.dump(data, outfile, ensure_ascii=False, indent=2)

def main():
    argparser = argparse.ArgumentParser(description='Fetches recipes and their metadata from chefkoch.de')

    mode_group = argparser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument('-d', '--daily', action='store_true',
        help='Downloads the recipe of the day, no further input required. Can be combined with -c and -r.')
    mode_group.add_argument('-s', '--search', action='store_true',
        help='Searches for the entered term and fetches the results. Can be combined with -n, -c and -r.')
    mode_group.add_argument('-u', '--url', action='store_true',
        help='Fetches the entered URLs. Can be combined with -c and -r.')
    mode_group.add_argument('-i', '--id', action='store_true',
        help='Fetches the entered IDs. Can be combined with -c and -r.')
    
    argparser.add_argument('-o', default='crawl', dest='outfolder',
        help='output folder')

    argparser.add_argument('-n', default=10, type=int, dest='num',
        help='number of elements to fetch')

    argparser.add_argument('-r', default=0, type=int, dest='recursion_depth',
        help='number of recursion steps')

    argparser.add_argument('-c', default=100, type=int, dest='comment_num',
        help='number of comments to load per recipe')

    argparser.add_argument('input', nargs='*',
        help='input arguments')

    global args
    args = argparser.parse_args()

    if args.daily:
        fetch_daily()
    elif args.search:
        print("Not yet implemented.")
    elif args.url:
        fetch_urls(args.input)
    elif args.id:
        fetch_ids(args.input)


if __name__ == "__main__":
    main()