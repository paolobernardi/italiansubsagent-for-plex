import hashlib
import StringIO
import zipfile
import re
from os.path import basename
from __builtin__ import sum, dir
from base64 import b64decode

try:
  from HTMLParser import HTMLParser
except ImportError:
  from html.parser import HTMLParser

from difflib import SequenceMatcher


PLUGIN_NAME = 'ItaliansSubsAgent'
ITASA_KEY = 'ZDJjYmJjY2FiYzAyZWIwNTJjMGI3NDQyYWEwN2U3OGQ='
ITASA_SHOWS = 'https://api.italiansubs.net/api/rest/shows?apikey={}'
ITASA_SHOW = 'https://api.italiansubs.net/api/rest/shows/{}?apikey={}'
ITASA_LOGIN = 'https://api.italiansubs.net/api/rest/users/login?username={}&password={}&apikey={}'
ITASA_USER = 'https://api.italiansubs.net/api/rest/users/?authcode={}&apikey={}'
ITASA_SUBTITLES = 'https://api.italiansubs.net/api/rest/subtitles?show_id={}&version={}&apikey={}'
ITASA_SUBTITLE_DOWNLOAD = 'https://api.italiansubs.net/api/rest/subtitles/download?subtitle_id={}&authcode={}&apikey={}'

def Start():
  HTTP.CacheTime = CACHE_1DAY * 7
  Log.Debug('ItaSubsAgent started!')
  HTTP.Headers['User-Agent'] = 'ItalianSubs Plugin for Plex (v2)'

def get_shows():
    Log.Debug('[ {} ] Getting shows list from ItalianSubs'.format(PLUGIN_NAME))
    r = HTTP.Request(ITASA_SHOWS.format(ITASA_KEY))
    root = XML.ElementFromString(r.content)

    results = []
    for tvshow in root.getiterator(tag='show'):
        try:
          id_t = tvshow.find('id').text.strip()
        except AttributeError:
          continue
        try:
          name_t = tvshow.find('name').text.strip()
        except AttributeError:
          continue
        results.append((name_t, id_t))
    
    if results:
      Log.Debug('[ {} ] Fetching done. There are {} shows'.format(PLUGIN_NAME, len(results)))
    else:
      Log.Debug('[ {} ]Fetching failed'.format(PLUGIN_NAME))    
    return results

def prepare_name(f):
    results = []
    f = f.strip().lower()
    f = f.split(' ')
    for each in f:
      each = each.strip()
      if each:
        results.append(each)
    return results


def verify_specialcase(filename):
  filename = basename(filename).lower()
  searches = {  'web-dl': re.search('web|webdl|web-dl', filename), 
                'dvdrip': re.search('dvd|dvdrip', filename), 
                'bluray': re.search('bluray|blueray', filename),
                'bdrip': re.search('bdrip|brip', filename),
                '720p': re.search('720', filename),
                '1080p': re.search('1080p', filename),
                '1080i': re.search('1080i', filename),
                #'hr': re.search('\bhr\b', filename),
                #'hdtv': re.search('hdtv', filename) 
              }
  for key, search in searches.items():
    if search:
      Log.Debug('[ {} ] Found special case: {}'.format(PLUGIN_NAME,key))
      return key
  Log.Debug('[ {} ] There is not special case for {}'.format(PLUGIN_NAME, filename))
  return 'Normale'


def doSearch(name, tvdb_id):
    Log.Debug('[ {} ] Searching the show {} in ItalianSubs shows'.format(PLUGIN_NAME,name))
    shows = get_shows()
    res = []
    junk = lambda x: x in ' of the'
    for name_show, id_show in shows:
      show_score = SequenceMatcher(junk, name, name_show).ratio()
      show_score = round(show_score * 100, 3)
      res.append((show_score, name_show, id_show))
    res = sorted(res, key=lambda x: -x[0])[:10]
    Log.Debug('[ {} ] Best show found: {}'.format(PLUGIN_NAME, res))
    for show_score, name_show, id_show in res:
      try:
        if tvdb_id == XML.ElementFromURL(ITASA_SHOW.format(id_show, ITASA_KEY)).find('.//id_tvdb').text:
          Log.Debug('[ {} ] Match found for {}. ID on ItalianSubs: {} (TvDbId method)'.format(PLUGIN_NAME,name, id_show))
          return id_show
      except:
        Log.Debug('[ {} ] 404 error for {}. ID on ItalianSubs: {}'.format(PLUGIN_NAME,name, id_show))
        continue
    try:
      show_score, name_show, id_show = res[0]
    except IndexError:
      pass
    else:
      if show_score > 75:
        Log.Debug('[ {} ] Match found for {}. ID on ItalianSubs: {} (Best score (>75) method)'.format(PLUGIN_NAME,name, id_show))
        return id_show
    Log.Debug('[ {} ] No matches found for {}'.format(PLUGIN_NAME, name))
    return None


def get_authcode_itasubs(username=None, password=None):
    Log.Debug('[ {} ] Testing authcode'.format(PLUGIN_NAME))
    authcode = Data.Load('authcode_itasa')
    status = XML.ElementFromURL(ITASA_USER.format(authcode, ITASA_KEY), cacheTime=0).find('status').text
    if status == 'fail':
      Log.Debug('[ {} ] Authcode not valid. Getting authcode'.format(PLUGIN_NAME))
      
      if username is None or password is None:
        username = Prefs['username1']
        password = Prefs['password1']

        #workaround for accented chars, inside preferences use htmlentities
        parser = HTMLParser()
        username = parser.unescape(username)
        password = parser.unescape(password)
      
      login = XML.ElementFromURL(ITASA_LOGIN.format(username, password, ITASA_KEY), cacheTime=0)
      if login.find('status').text == 'fail':
        Log.Debug('[ {} ] Fetching authcode failed. Error at login, verify username and passowrd'.format(PLUGIN_NAME))
        return None
      authcode = login.find('.//authcode').text
      Data.Save('authcode_itasa', authcode)
      Log.Debug('[ {} ] Got authcode. It is saved'.format(PLUGIN_NAME))
    Log.Debug('[ {} ] Authcode OK'.format(PLUGIN_NAME))
    return authcode


def login_itasubs(username=None, password=None):
    if username is None or password is None:
      username = Prefs['username1']
      password = Prefs['password1']

      #workaround for accented chars, inside preferences use htmlentities instead of accented chars
      parser = HTMLParser()
      username = parser.unescape(username)
      password = parser.unescape(password)
    
    r = HTTP.Request('http://www.italiansubs.net/index.php', cacheTime=0)
    root = HTML.ElementFromString(r.content)
    login_form = root.get_element_by_id('form-login')

    Log.Debug('[ {} ] Testing cookies if they are still valid'.format(PLUGIN_NAME))

    if 'ciao '+Prefs['username1'].lower() in login_form.text_content().lower():
      Log.Debug('[ {} ] Cookies are valid. Login OK'.format(PLUGIN_NAME))
      return None

    Log.Debug('[ {} ] Cookies not valid or expired. Trying to login'.format(PLUGIN_NAME))
    
    data = {}

    for el in login_form:
        if 'type' in el.attrib:
            if el.attrib['type'] == 'hidden':
                data[el.attrib['name']] = el.attrib['value']

    data.update({'username':username, 'passwd': password})
    r = HTTP.Request('http://www.italiansubs.net/index.php', values=data)
    HTTP.CookiesForURL('http://www.italiansubs.net/')
    Log.Debug('[ {} ] Login done. Cookies saved'.format(PLUGIN_NAME))
    return None


ITASA_KEY = b64decode(ITASA_KEY)


def get_subtitle(id_s, season, episode, kind, name_show):

    authcode = get_authcode_itasubs()
    login_itasubs()
    if authcode is None:
      Log.Debug(authcode)
      return None
    id_file = False

    Log.Debug('[ {} ] Searching the subtitle for episode s{}e{} of {}. Special case: {}'.format(PLUGIN_NAME, season, episode, name_show, 'Nothing' if kind == 'Normale' else kind))

    pattern = season+'x'+episode
    season = '0'+season
    subtitles = XML.ElementFromURL(ITASA_SUBTITLES.format(id_s, kind, ITASA_KEY), cacheTime=0)
    while True:
      for subtitle in subtitles.getiterator('subtitle'):
        name = subtitle.find('name').text.lower().strip()
        if pattern in name:
          Log.Debug('[ {} ] Subtitle s{}e{} of {} found!'.format(PLUGIN_NAME, season, episode, name_show))
          id_file = subtitle.find('id').text.strip()
          break
      if id_file:
        break
      try:
        next_page = subtitles.find('.//next').text
      except AttributeError:
        next_page = False
      if next_page:
        Log.Debug('[ {} ] Subtitle still not found. Search in next page'.format(PLUGIN_NAME))
        subtitles = XML.ElementFromURL(next_page, cacheTime=0)
      elif kind != 'Normale':
        Log.Debug('[ {} ] Subtitle with special case {} not found. Switching to normal case'.format(PLUGIN_NAME, kind))
        subtitles = XML.ElementFromURL(ITASA_SUBTITLES.format(id_s, 'Normale', ITASA_KEY), cacheTime=0)
      else:
        Log.Debug('[ {} ] Subtitle NOT FOUND for s{}e{} of {}'.format(PLUGIN_NAME, season, episode, name_show))
        break

    if id_file:
      url = ITASA_SUBTITLE_DOWNLOAD.format(id_file, authcode, ITASA_KEY)
      r = HTTP.Request(url, cacheTime=0)
      bfr = StringIO.StringIO()
      bfr.write(r.content)
      bfr.flush()
      Log.Debug('[ {} ] Subtitle s{}e{} of {} downloaded (Zip Archive)'.format(PLUGIN_NAME, season, episode, name_show))
      return (hashlib.md5(url).hexdigest(), bfr)

    Log.Debug('[ {} ] Subtitle not found'.format(PLUGIN_NAME))
    return None


def unzip(bfr, episode=None):
  Log.Debug('[ {} ] Try to extract the subtitle from Zip Archive'.format(PLUGIN_NAME))
  z = zipfile.ZipFile(bfr)
  regex_episode = re.compile('s(?P<season>\d+)e(?P<episode>\d+)')
  for name in z.namelist():
    if episode:
      search = re.search(regex_episode, name.lower())
      if search:
        if int(search.group('episode')) == int(episode):
          subtitle = z.open(name)
          Log.Debug('[ {} ] Subtitle extracted successfully'.format(PLUGIN_NAME))
          return subtitle.read()
  Log.Debug('[ {} ] Error during extraction'.format(PLUGIN_NAME))
  return None

def search_subtitle(name, filename, season, episode, tvdb_id):
  id_show = doSearch(name, tvdb_id)
  kind = verify_specialcase(filename)
  if id_show:
    subtitle = get_subtitle(id_show, season, episode, kind, name)
    if subtitle:
      subtitle_url, subtitle_contents = subtitle
      subtitle_contents = unzip(subtitle_contents, episode)
      return (subtitle_url, subtitle_contents)
  return None




class ItalianSubsAgent(Agent.TV_Shows):

  name = 'ItalianSubsAgent'
  languages = [Locale.Language.English, ]
  primary_provider = False

  def search(self, results, media, lang, manual=True):
    results.Append(MetadataSearchResult(id = 'null', score = 100))


  def update(self, metadata, media, lang, force=True):
    force = True
    for s in media.seasons:
      for e in media.seasons[s].episodes:
        for i in media.seasons[s].episodes[e].items:
          for part in i.parts:
            name = media.title
            filename = part.file
            season = str(s)
            episode = str(e)
            episode = '0'+episode if len(episode) == 1 else episode
            if 'thetvdb' in media.guid.lower():
              tvdb_id = media.guid.split('//')[::-1][0].split('?')[0].strip()
            else:
              tvdb_id = None
            subtitle = search_subtitle(name, filename, season, episode, tvdb_id)
            if subtitle:
              subtitle_url, subtitle_contents = subtitle
              Log.Debug('[ {} ] Subtitle for {} s{}e{} ({}) downloaded and installed successfully! :)'.format(PLUGIN_NAME,name, season, episode, basename(filename)))
              part.subtitles['it'][subtitle_url] = Proxy.Media(subtitle_contents, ext='srt')
            else:
              Log.Debug('[ {} ] Subtitle for {} s{}e{} ({}) NOT available, sorry! :('.format(PLUGIN_NAME,name, season, episode, basename(filename)))
