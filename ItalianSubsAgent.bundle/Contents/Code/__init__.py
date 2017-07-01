import hashlib
import os
import io
import time
from StringIO import StringIO
from zipfile import ZipFile
from __builtin__ import dir
from base64 import b64decode
from difflib import SequenceMatcher
try:
    from HTMLParser import HTMLParser
except ImportError:
    from html.parser import HTMLParser


PLUGIN_NAME = 'ItaliansSubsAgent'
ITASA_KEY = 'ZDJjYmJjY2FiYzAyZWIwNTJjMGI3NDQyYWEwN2U3OGQ='
ITASA_SHOWS = 'https://api.italiansubs.net/api/rest/shows?apikey={}'
ITASA_SHOW = 'https://api.italiansubs.net/api/rest/shows/{}?apikey={}'
ITASA_LOGIN = 'https://api.italiansubs.net/api/rest/users/login?username={}&password={}&apikey={}'
ITASA_USER = 'https://api.italiansubs.net/api/rest/users/?authcode={}&apikey={}'
ITASA_SUBTITLES = 'https://api.italiansubs.net/api/rest/subtitles?show_id={}&version=&apikey={}'
ITASA_SUBTITLES_SEARCH = 'https://api.italiansubs.net/api/rest/subtitles/search?q={query}&show_id={id_show}&version=&apikey={apikey}'
ITASA_SUBTITLE_DOWNLOAD = 'https://api.italiansubs.net/api/rest/subtitles/download?subtitle_id={}&authcode={}&apikey={}'


def Start():
    HTTP.CacheTime = CACHE_1DAY * 7
    Log.Debug('ItaSubsAgent started!')
    HTTP.Headers['User-Agent'] = 'ItalianSubs Plugin for Plex (v2)'


class Shows(object):
    SHOWS_URL = 'https://api.italiansubs.net/api/rest/shows?apikey={apikey}'
    SHOW_URL = 'https://api.italiansubs.net/api/rest/shows/{id_show}?apikey={apikey}'
    SLEEP_TIME = 3

    def __init__(self, name_show, tvdb_id=None):
        self.name_show = name_show
        self.tvdb_id = tvdb_id
        self.get_shows_list()
        Log.Debug('[ {} ] Searching the show {} (TVDBid: {}) in ItalianSubs shows'.format(PLUGIN_NAME, name_show, tvdb_id))

    def get_shows_list(self):
        Log.Debug('[ {} ] Getting shows list from ItalianSubs'.format(PLUGIN_NAME))
        shows = XML.ElementFromURL(self.SHOWS_URL.format(apikey=ITASA_KEY))
        res = []
        for show in shows.getiterator(tag='show'):
            try:
                id_show = show.find('id').text.strip()
            except AttributeError:
                continue
            try:
                name_show = show.find('name').text.strip()
            except AttributeError:
                continue
            if name_show and id_show:
                res.append((name_show, id_show))
        Log.Debug('[ {} ] Fetching done. There are {} shows'.format(PLUGIN_NAME, len(res)))
        self.shows_list = res
        return None

    def get_id_show(self):
        res = []
        junk = lambda x: x in ' of the \'s :'
        for name_show, id_show in self.shows_list:
            show_score = SequenceMatcher(junk, self.name_show, name_show).ratio()
            show_score = round(show_score * 100, 3)
            res.append((show_score, name_show, id_show))
        res = sorted(res, key=lambda x: -x[0])[:50]
        Log.Debug('[ {} ] Best show found: {}'.format(PLUGIN_NAME, res))
        for i, (show_score, name_show, id_show) in enumerate(res):
            try:
                tvdb_id = XML.ElementFromURL(self.SHOW_URL.format(id_show=id_show, apikey=ITASA_KEY)).find('.//id_tvdb').text
            except:
                Log.Debug('[ {} ] 404 error for {}. ID on ItalianSubs: {}'.format(PLUGIN_NAME, self.name_show, id_show))
                continue
            if self.tvdb_id == tvdb_id:
                Log.Debug('[ {} ] Match found for {}. ID on ItalianSubs: {} (TvDbId method)'.format(PLUGIN_NAME, self.name_show, id_show))
                return id_show
            if i % 10 == 0:
                Log.Debug('[ {} ] Evaluated 10 shows. Pause for {} secs'.format(PLUGIN_NAME, self.SLEEP_TIME))
                time.sleep(self.SLEEP_TIME)
        try:
            show_score, name_show, id_show = res[0]
        except IndexError:
            pass
        else:
            if show_score > 75:
                Log.Debug('[ {} ] Match found for {}. ID on ItalianSubs: {} (Best score (>75) method)'.format(PLUGIN_NAME, self.name_show, id_show))
                return id_show
        Log.Debug('[ {} ] No matches found for {} (TVDBid: {})'.format(PLUGIN_NAME, self.name_show, self.tvdb_id))
        return None


class Login_Itasa(object):
    LOGIN_URL = 'https://api.italiansubs.net/api/rest/users/login?username={username}&password={password}&apikey={apikey}'
    USER_URL = 'https://api.italiansubs.net/api/rest/users/?authcode={authcode}&apikey={apikey}'
    ITASA_HOME = 'https://www.italiansubs.net/'

    def __init__(self):
        self.get_credentials()
        self.authcode = Data.Load('authcode_itasa')

    def get_credentials(self):
        Log.Debug('[ {} ] Loading Itasa credentials..'.format(PLUGIN_NAME))
        username = Prefs['username1']
        password = Prefs['password1']
        #workaround for accented chars, inside preferences use htmlentities
        parser = HTMLParser()
        username = parser.unescape(username)
        password = parser.unescape(password)
        self.username = username
        self.password = password
        if not username or not password:
            Log.Debug('[ {} ] Username and password not set, impossible to continue.'.format(PLUGIN_NAME))

    def do_authcode(self):
        try:
            login = XML.ElementFromURL(self.LOGIN_URL.format(username=self.username, password=self.password, apikey=ITASA_KEY), cacheTime=0)
        except:
            Log.Debug('[ {} ] Error during connection for retrieving the authcode')
            return None
        if login.find('status').text == 'success':
            authcode = login.find('.//authcode').text
            Data.Save('authcode_itasa', authcode)
            Log.Debug('[ {} ] Got Authcode. Authcode ok.'.format(PLUGIN_NAME))
            self.authcode = authcode
            return None
        Log.Debug('[ {} ] Authcode retrieving failed. Impossible to continue'.format(PLUGIN_NAME))
        return None

    def do_login(self):
        login_form = HTML.ElementFromURL(self.ITASA_HOME, cacheTime=0).get_element_by_id('form-login')
        data_login = {'username': self.username, 'passwd': self.password}
        for el in login_form:
            try:
                if el.attrib['type'] == 'hidden':
                    data_login[el.attrib['name']] = el.attrib['value']
            except KeyError:
                continue
        req = HTTP.Request(self.ITASA_HOME, values=data_login, cacheTime=0)
        HTTP.CookiesForURL(self.ITASA_HOME)
        if 'nome utente e password non sono corrette' not in req.content.lower():
            Log.Debug('[ {} ] Login failed. Are Username/Password correct?'.format(PLUGIN_NAME))
            return None
        if 'ciao ' + self.username.lower() not in req.content.lower():
            Log.Debug('[ {} ] Login failed. Unknown error.'.format(PLUGIN_NAME))
            return None
        Log.Debug('[ {} ] Login done. Cookies saved'.format(PLUGIN_NAME))


ITASA_KEY = b64decode(ITASA_KEY)


class Subtitles(object):
    def __init__(self, id_show, name_show, filename, season, episode):
        self.id_show = id_show
        self.name_show = name_show
        self.filename = filename
        self.season = '{season}'.format(season=season)
        self.episode = '{episode}'.format(episode=episode.zfill(2))
        self.specialcase = self.detect_specialcase()
        Log.Debug('[ {} ] Found special case: {}'.format(PLUGIN_NAME, self.specialcase)) if self.specialcase else ''
        self.all_subs = Prefs['all_subs']
        self.copy_subs = Prefs['copy_subs']
        self.extract_all = False
        self.subtitles = []

    def detect_specialcase(self):
        filename = os.path.basename(self.filename).lower()
        if 'web' in filename:
            return 'web-dl'
        if 'dvd' in filename:
            return 'dvdrip'
        if 'bluray' in filename or 'blueray' in filename:
            return 'bluray'
        if 'brip' in filename or 'bdrip' in filename:
            return 'bdrip'
        if '720' in filename:
            return '720p'
        if '1080p' in filename:
            return '1080p'
        if '1080i' in filename:
            return '1080i'
        if '1080' in filename:
            return '1080'
        return None

    def search(self, complete=False):
        query = '{season} completa'.format(season=self.season) if complete else '{season}x{episode}'.format(season=self.season, episode=self.episode)
        subtitles = XML.ElementFromURL(ITASA_SUBTITLES_SEARCH.format(query=query, id_show=self.id_show, apikey=ITASA_KEY))
        res = []
        for subtitle in subtitles.getiterator('subtitle'):
            subtitle = {
                'id': subtitle.find('id').text,
                'name': subtitle.find('name').text,
                'version': subtitle.find('version').text.lower(),
                'complete': complete,
                'subs': []
            }
            if subtitle not in res:
                res.append(subtitle)
        return res

    def filter(self, subtitles):
        if self.all_subs:
            return subtitles
        if len(subtitles) < 2:
            return subtitles
        if self.specialcase:
            subtitles = [sub for sub in subtitles if sub['version'] == self.specialcase]
            if subtitles:
                return subtitles
        return [sub for sub in subtitles if sub['version'] == 'normale']

    def download(self, subtitles):
        login = Login_Itasa()
        for subtitle in subtitles:
            content_type = ''
            attempts = 0
            while 'application/zip' not in content_type:
                url = ITASA_SUBTITLE_DOWNLOAD.format(subtitle['id'], login.authcode, ITASA_KEY)
                file = HTTP.Request(url, cacheTime=0)
                content_type = file.headers['content-type']
                if 'text/xml' in content_type:
                    Log.Debug('[ {} ] Authcode not valid. Trying to retrieve it..'.format(PLUGIN_NAME))
                    login.do_authcode()
                if 'text/html' in content_type and 'utenti registrati' in file.content:
                    Log.Debug('[ {} ] Not logged. Trying to log in'.format(PLUGIN_NAME))
                    login.do_login()
                if 'text/html' in content_type and 'limite di download' in file.content:
                    Log.Debug('[ {} ] You have reached the download limit for this subtitle'.format(PLUGIN_NAME))
                    break
                if attempts > 5:
                    break
                attempts += 1
            filebuffer = StringIO()
            filebuffer.write(file)
            filebuffer.flush()
            Log.Debug('[ {} ] Subtitle {} (id: {}) downloaded!'.format(PLUGIN_NAME, subtitle['name'], subtitle['id']))
            for sub_content in self.unzip(filebuffer):
                sub_hash = hashlib.md5(sub_content).hexdigest()
                subtitle['subs'].append((sub_hash, sub_content))
        return subtitles

    def unzip(self, zipfile):
        episode = 's{season}e{episode}'.format(season=self.season.zfill(2), episode=self.episode)
        res = []
        try:
            zipfile = ZipFile(zipfile)
        except:
            Log.Debug('[ {} ] Error opening the ZipFile'.format(PLUGIN_NAME))
            return res
        for name_sub in zipfile.namelist():
            if episode in name_sub.lower() or self.extract_all:
                try:
                    sub_content = zipfile.open(name_sub).read()
                except:
                    Log.Debug('[ {} ] Error extracting the subtitle from ZipFile'.format(PLUGIN_NAME))
                    continue
                res.append(sub_content)
                Log.Debug('[ {} ] Subtitle {} extracted!'.format(PLUGIN_NAME, name_sub))
        if not res:
            Log.Debug('[ {} ] Subtitle {}x{} for {} is not present in zipfile'.format(PLUGIN_NAME, self.season, self.episode, self.name_show))
        return res

    def save(self, subtitles):
        Log.Debug('[ {} ] Copying subtitles for {}x{} alongside the file {}'.format(PLUGIN_NAME, self.season, self.episode, self.filename))
        path, filename = os.path.split(self.filename)
        filename, ext = os.path.splitext(filename)
        i = 1
        for subtitle in subtitles:
            for sub_hash, sub_content in subtitle['subs']:
                textToappend = '.it{}.srt'.format(i)
                with io.open(os.path.join(path, filename + textToappend), 'wb') as f:
                    f.write(sub_content)
                Log.Debug('[ {} ] Subtitle {} (Version: {}) copied in {}!'.format(PLUGIN_NAME, filename, subtitle['version'], path))
                i += 1

    def get(self):
        Log.Debug('[ {} ] Searching subtitles for {} {}x{} ..'.format(PLUGIN_NAME, self.name_show, self.season, self.episode))
        subtitles = self.search(complete=False)
        subtitles_version = set([sub['version'] for sub in subtitles])
        Log.Debug('[ {} ] Found {} subtitles (Version: {})'.format(PLUGIN_NAME, len(subtitles), ', '.join(subtitles_version)))
        subtitles_complete = [sub for sub in self.search(complete=True) if sub['version'] not in subtitles_version]
        Log.Debug('[ {} ] Found {} complete pack for season {} (Version: {})'.format(PLUGIN_NAME, len(subtitles_complete), self.season, ', '.join(set([sub['version'] for sub in subtitles_complete]))))
        subtitles += subtitles_complete
        subtitles = self.filter(subtitles)
        Log.Debug('[ {} ] Subtitles filtered. Remaining {} subtitles (Version: {}, All subs: {}, Special Case: {})'.format(PLUGIN_NAME, len(subtitles), ', '.join([sub['version'] for sub in subtitles]), self.all_subs, self.specialcase))
        if not subtitles:
            Log.Debug('[ {} ] No subtitles found for {} {}x{}!'.format(PLUGIN_NAME, self.name_show, self.season, self.episode))
            return self
        Log.Debug('[ {} ] Start downloading subtitles...'.format(PLUGIN_NAME))
        subtitles = self.download(subtitles)
        if not [sub['subs'] for sub in subtitles if sub['subs']]:
            Log.Debug('[ {} ] No subtitles found for {} {}x{}!'.format(PLUGIN_NAME, self.name_show, self.season, self.episode))
            return self
        if self.copy_subs:
            self.save(subtitles)
        self.subtitles = subtitles
        return self

    def return_subtitles(self):
        return [(sub_hash, sub_content) for subtitle in self.subtitles for sub_hash, sub_content in subtitle['subs']]


class Subtitles_Movies(Subtitles):
    SLEEP_TIME = 2

    def __init__(self, name_movie, filename):
        self.id_show = ''
        self.name_show = name_movie
        self.name_movie = name_movie
        self.filename = filename
        self.season = ''
        self.episode = ''
        self.specialcase = self.detect_specialcase()
        Log.Debug('[ {} ] Found special case: {}'.format(PLUGIN_NAME, self.specialcase)) if self.specialcase else ''
        self.all_subs = Prefs['all_subs']
        self.copy_subs = Prefs['copy_subs']
        self.extract_all = True
        self.subtitles = []

    def search(self, complete=None):
        if complete:
            return []
        Log.Debug('[ {} ] Start searching movie {} ..'.format(PLUGIN_NAME, self.name_movie))
        movie = self.search_movies(name_movie=self.name_movie)
        if movie:
            return self.search_movies(name_movie=movie['name'], all_versions=True)
        return []

    def search_movies(self, name_movie, all_versions=None):
        url = ITASA_SUBTITLES_SEARCH.format(query=name_movie if all_versions else '', id_show=8, apikey=ITASA_KEY)
        res = []
        junk = lambda x: x in ' of the'
        while True:
            subtitles = XML.ElementFromURL(url)
            for subtitle in subtitles.getiterator('subtitle'):
                name = subtitle.find('name').text
                subtitle = {
                    'name': name,
                    'id': subtitle.find('id').text,
                    'version': subtitle.find('version').text.lower(),
                    'subs': [],
                    'score': round(SequenceMatcher(junk, name_movie, name).ratio() * 100, 3)
                }
                if subtitle not in res:
                    res.append(subtitle)
            if all_versions:
                return res
            res = sorted(res, key=lambda movie: -movie['score'])
            try:
                best_movie = res[0]
            except IndexError:
                pass
            else:
                if best_movie['score'] > 90:
                    Log.Debug('[ {} ] Match found for {}. ID on ItalianSubs: {} (Best score (>90) method)'.format(PLUGIN_NAME, self.name_movie, best_movie['id']))
                    return best_movie
            next_page = subtitles.find('.//next').text
            if next_page:
                res = []
                url = next_page.strip()
                Log.Debug('[ {} ] No movies found yet. Trying to scan the next page. Pausing for {} secs'.format(PLUGIN_NAME, self.SLEEP_TIME))
                time.sleep(self.SLEEP_TIME)
            else:
                break
        return None


def get_tvdb_id(guid):
    if 'thetvdb' not in guid:
        return 0
    try:
        tvdb_id = guid.split('//')[::-1][0].split('?')[0].strip()
    except:
        return 0
    return tvdb_id


def add_subtitles(part, subtitles, name, season=None, episode=None):
    donot_add = Prefs['donot_add']
    if donot_add:
        Log.Debug('[ {} ] Subtitle not added. Do not add to Plex option was selected'.format(PLUGIN_NAME))
        return None
    if season and episode:
        episode = ' {season}x{episode}'.format(season=season, episode=episode.zfill(2))
    else:
        episode = ''
    if not subtitles:
        Log.Debug('[ {} ] Subtitle for {name}{episode} NOT added!'.format(PLUGIN_NAME, name=name, episode=episode))
    for sub_hash, sub_content in subtitles:
        part.subtitles['it'][sub_hash] = Proxy.Media(sub_content, ext='srt')
        Log.Debug('[ {} ] Subtitle for {name}{episode} added!'.format(PLUGIN_NAME, name=name, episode=episode))
    return None


class ItalianSubsAgent(Agent.TV_Shows):
    name = 'ItalianSubsAgent'
    languages = [Locale.Language.English, ]
    primary_provider = False

    def search(self, results, media, lang, manual=True):
        results.Append(MetadataSearchResult(id='null', score=100))

    def update(self, metadata, media, lang, force=True):
        for season in media.seasons:
            for episode in media.seasons[season].episodes:
                for items in media.seasons[season].episodes[episode].items:
                    for part in items.parts:
                        season = str(season)
                        episode = str(episode)
                        name_show = media.title
                        tvdb_id = get_tvdb_id(media.guid)
                        filename = part.file
                        id_show = Shows(name_show, tvdb_id).get_id_show()
                        if not id_show:
                            return None
                        subtitles = Subtitles(id_show, name_show, filename, season, episode).get().return_subtitles()
                        add_subtitles(part, subtitles, name_show, season, episode)


class ItalianSubsAgentMovies(Agent.Movies):
    name = 'ItalianSubsAgent'
    languages = [Locale.Language.English, ]
    primary_provider = False

    def search(self, results, media, lang, manual=True):
        results.Append(MetadataSearchResult(id='null', score=100))

    def update(self, metadata, media, lang, force=True):
        for items in media.items:
            for part in items.parts:
                name_movie = media.title
                filename = part.file
                subtitles = Subtitles_Movies(name_movie, filename).get().return_subtitles()
                add_subtitles(part, subtitles, name_movie)
