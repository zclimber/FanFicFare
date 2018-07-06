# -*- coding: utf-8 -*-

# Copyright 2011 Fanficdownloader team, 2017 FanFicFare team
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import logging
logger = logging.getLogger(__name__)
import re
import urllib2


from ..htmlcleanup import stripHTML
from .. import exceptions as exceptions

from base_adapter import BaseSiteAdapter,  makeDate

class HarryPotterFanFictionComSiteAdapter(BaseSiteAdapter):

    def __init__(self, config, url):
        BaseSiteAdapter.__init__(self, config, url)
        self.story.setMetadata('siteabbrev','hp')
        self.is_adult=False

        # get storyId from url--url validation guarantees query is only psid=1234
        self.story.setMetadata('storyId',self.parsedUrl.query.split('=',)[1])

        # The date format will vary from site to site.
        # http://docs.python.org/library/datetime.html#strftime-strptime-behavior
        self.dateformat = "%Y-%m-%d %H:%M:%S"

        # normalized story URL.
        self._setURL('https://' + self.getSiteDomain() + '/viewstory.php?psid='+self.story.getMetadata('storyId'))


    @staticmethod
    def getSiteDomain():
        return 'harrypotterfanfiction.com'

    @classmethod
    def getSiteExampleURLs(cls):
        return "https://harrypotterfanfiction.com/viewstory.php?psid=1234"

    def getSiteURLPattern(self):
        return r"https?"+re.escape("://")+r"(www\.)?"+re.escape("harrypotterfanfiction.com/viewstory.php?psid=")+r"\d+$"

    def use_pagecache(self):
        '''
        adapters that will work with the page cache need to implement
        this and change it to True.
        '''
        return True

    def extractChapterUrlsAndMetadata(self):

        url = self.url
        logger.debug("URL: "+url)

        try:
            data = self._fetchUrl(url)
        except urllib2.HTTPError, e:
            if e.code == 404:
                raise exceptions.StoryDoesNotExist(self.url)
            else:
                raise e

        ## Don't know if these still apply
        # if "Access denied. This story has not been validated by the adminstrators of this site." in data:
        #     raise exceptions.AccessDenied(self.getSiteDomain() +" says: Access denied. This story has not been validated by the adminstrators of this site.")
        # elif "ERROR locating story meta for psid" in data:
        #     raise exceptions.StoryDoesNotExist(self.url)

        # use BeautifulSoup HTML parser to make everything easier to find.
        soup = self.make_soup(data)

        ## Title
        h2 = soup.find('h2')
        h2.find('i').extract() # remove author
        self.story.setMetadata('title',stripHTML(h2))
        ## Don't know if these still apply
        ## javascript:if (confirm('Please note. This story may contain adult themes. By clicking here you are stating that you are over 17. Click cancel if you do not meet this requirement.')) location = '?psid=290995'
        # if "This story may contain adult themes." in a['href'] and not (self.is_adult or self.getConfig("is_adult")):
        #     raise exceptions.AdultCheckRequired(self.url)


        # Find authorid and URL from... author url.
        a = soup.find('a', href=re.compile(r"viewuser.php\?uid=\d+"))
        self.story.setMetadata('authorId',a['href'].split('=')[1])
        self.story.setMetadata('authorUrl','https://'+self.host+'/'+a['href'])
        self.story.setMetadata('author',a.string[3:]) # remove 'by '

        ## hpcom doesn't always give us total words--but it does give
        ## us words/chapter.  I'd rather add than fetch and parse
        ## another page.
        chapter_words=0
        for tr in soup.find('table',{'class':'table-chapters'}).find('tbody').findAll('tr'):
            tdstr = tr.findAll('td')[2].string
            if tdstr and tdstr.isdigit():
                chapter_words+=int(tdstr)
            chapter = tr.find('a')
            chpt=re.sub(r'^.*?(\?chapterid=\d+).*?',r'\1',chapter['href'])
            self.chapterUrls.append((stripHTML(chapter),'https://'+self.host+'/viewstory.php'+chpt))
        #self.story.setMetadata('numWords',unicode(words))
        self.story.setMetadata('numChapters',len(self.chapterUrls))

        ## Finding the metadata is a bit of a pain.  Desc is the only thing this color.
        desctable= soup.find('table',{'bgcolor':'#f0e8e8'})
        #self.setDescription(url,desctable)
        #self.story.setMetadata('description',stripHTML(desctable))

        # <div class='entry'>
        # <div class='entry__key'>Rating</div>
        # <div class='entry__value'>Mature</div>
        # </div>

        meta_key_map = {
            'Rating':'rating',
            'Words':'numWords',
            'Characters':'characters',
            'Genre(s)':'genre',
            'Era':'era',
            'Advisory':'warnings',
            'Story Reviews':'reviews',
#            'Status':'', # Status is treated special
            'First Published':'datePublished',
            'Last Updated':'dateUpdated',
            }
        for key in soup.find_all('div',{'class':'entry__key'}):
            value = stripHTML(key.find_next('div',{'class':'entry__value'}))
            key = stripHTML(key)
            meta = meta_key_map.get(key,None)
            if meta:
                if meta.startswith('date'):
                    value = makeDate(value,self.dateformat)
                self.story.setMetadata(meta,value)
            if key == 'Status':
                if value == 'WIP':
                    value = 'In-Progress'
                elif value == 'COMPLETED':
                    value = 'Completed'
                # 'Abandoned' and other possible values used as-is
                self.story.setMetadata('status',value)

        # older stories don't present total words, use sum from chapters.
        if not self.story.getMetadata('numWords'):
            self.story.setMetadata('numWords',chapter_words)

    def getChapterText(self, url):

        logger.debug('Getting chapter text from: %s' % url)

        data = self._fetchUrl(url)

        # try:
        #     # remove everything after here--the site's chapters break
        #     # the BS4 parser.
        #     data = data[:data.index('<script type="text/javascript" src="reviewjs.js">')]
        # except:
        #     # some older stories don't have the code at the end that breaks things.
        #     pass
        
        soup = self.make_soup(data)

        div = soup.find('div', {'style' : 'line-height: 1.5'})

        if None == div:
            raise exceptions.FailedToDownload("Error downloading Chapter: %s!  Missing required element!" % url)

        return self.utf8FromSoup(url,div)

def getClass():
    return HarryPotterFanFictionComSiteAdapter