import urllib2
import urlparse
import sqlite3
import re
from bs4 import BeautifulSoup
from urlparse import urljoin
from pysqlite2 import dbapi2 as sqlite

# Create a list of words to ignore
ignorewords=set(['the','of','to','and','a','in','is','it'])

class crawler:
    # Initialize the crawler with the name of database 
    def __init__(self,dbname):
        self.conn=sqlite.connect(dbname)

    def __del__(self): 
        self.conn.close()
    
    def dbcommit(self):
         self.conn.commit()
    # Auxilliary function for getting an entry id and adding
    # it if it's not present
    def getentryid(self,table,field,value,createnew=True):
        cur=self.conn.execute(
        "select rowid from %s where %s='%s'" % (table,field,value)) 
        res=cur.fetchone()
        if res==None:
            cur=self.conn.execute(
            "insert into %s (%s) values ('%s')" % (table,field,value))
            return cur.lastrowid
        else:
            return res[0]
    
    # Index an individual page
    def addtoindex(self,url,soup):
        if self.isindexed(url): return
        print 'Indexing %s' % url
        # Get the individual words
        text=self.gettextonly(soup)
        words=self.separatewords(text)
        # Get the URL id, create new is true
        urlid=self.getentryid('urllist','url',url)
        # Link each word to this url
        for i in range(len(words)):
            word=words[i]
            if word in ignorewords: continue
            wordid=self.getentryid('wordlist','word',word)
            self.conn.execute("insert into wordlocation(urlid,wordid,location) \
                values (%d,%d,%d)" % (urlid,wordid,i))
    
    # Extract the text from an HTML page (**no tags**)
    def gettextonly(self,soup):
        v=soup.string
        if(v==None):
            c=soup.contents
            resulttext=''
            for t in c:
                subtext=self.gettextonly(t)
                resulttext+=subtext+'\n'
            return resulttext
        else:
            return v.strip()
    
    # Separate the words by any non-whitespace character
    def separatewords(self,text):
        splitter=re.compile('\\W*')
        return [s.lower() for s in splitter.split(text) if s!='']
    
    # Return true if this url is already indexed
    def isindexed(self,url):
        u=self.conn.execute(
        "select rowid from urllist where url='%s'" % url).fetchone() 
        if u!=None:
            # Check if it has actually been crawled
            v=self.conn.execute(
            'select * from wordlocation where urlid=%d' % u[0]).fetchone() 
            if v!=None: return True
        return False
    
    # Add a link between two pages
    def addlinkref(self,urlFrom,urlTo,linkText):
        pass
      
    # Starting with a list of pages, do a breadth
    # first search to the given depth, indexing pages
    # as we go
    def crawl(self,pages,depth=2):
        for i in range(depth):
            newpages=set()
            for page in pages:
                try:
                    c=urllib2.urlopen(page)
                except:
                    print "Could not open %s" % page
                    continue
                soup=BeautifulSoup(c.read(),"html.parser")
                self.addtoindex(page,soup)

                links=soup('a')
                for link in links:
                    if('href' in dict(link.attrs)):
                        url=urljoin(page,link['href'])
                        if url.find("'")!=-1: continue
                        url=url.split('#')[0] #remove the location portion
                        # check the page wether has been indexed
                        if(url[0:4]=='http' and not self.isindexed(url)):
                            newpages.add(url)
                        linkText=self.gettextonly(link)
                        self.addlinkref(page,url,linkText)
                self.dbcommit()
            pages=newpages
    
    # Create the database tables
    def createindextables(self):
        self.conn.execute('create table urllist(url)')
        self.conn.execute('create table wordlist(word)')
        self.conn.execute('create table wordlocation(urlid,wordid,location)')
        self.conn.execute('create table link(fromid integer,toid integer)')
        self.conn.execute('create table linkwords(wordid,linkid)')
        self.conn.execute('create index wordidx on wordlist(word)')
        self.conn.execute('create index urlidx on urllist(url)')
        self.conn.execute('create index wordurlidx on wordlocation(wordid)')
        self.conn.execute('create index urltoidx on link(toid)') 
        self.conn.execute('create index urlfromidx on link(fromid)') 
        self.dbcommit()

class searcher:
    def __init__(self,dbname):
        self.conn=sqlite.connect(dbname)

    def __del__(self): 
        self.conn.close()

    def getmatchrows(self,q):
        # Strings to build the query
        fieldlist='w0.urlid'
        tablelist=''
        clauselist=''
        wordids=[]
        # Split the words by spaces
        words=q.split(' ')
        tablenumber=0
        for word in words:
            # Get the word ID
            wordrow=self.conn.execute(
                "select rowid from wordlist where word='%s'" % word).fetchone()
            if wordrow!=None:
                wordid=wordrow[0]
                wordids.append(wordid)
                if tablenumber>0:
                    tablelist+=','
                    clauselist+=' and '
                    clauselist+='w%d.urlid=w%d.urlid and ' % (tablenumber-1,tablenumber)
                fieldlist+=',w%d.location' % tablenumber
                tablelist+='wordlocation w%d' % tablenumber
                clauselist+='w%d.wordid=%d' % (tablenumber,wordid)
                tablenumber+=1
        if(len(clauselist.strip())==0):return None
        # Create the query from the separate parts
        fullquery='select %s from %s where %s' % (fieldlist,tablelist,clauselist)
        print(fullquery)
        cur=self.conn.execute(fullquery)
        rows=[row for row in cur]
        return rows,wordids


    def getscoredlist(self,rows,wordids):
        # row fromat : [urlid, loc1, loc2...]
        totalscores=dict([(row[0],0) for row in rows])
        # This is where you'll later put the scoring functions
        weights=[]
        weights=[(1.0,self.frequencyscore(rows)),
                (1.5,self.locationscore(rows))]
        for (weight,scores) in weights:
            for url in totalscores:
                totalscores[url]+=weight*scores[url]
        return totalscores

    def geturlname(self,id):
        return self.conn.execute(
            "select url from urllist where rowid=%d" % id).fetchone()[0]

    def query(self,q):
        rows,wordids=self.getmatchrows(q)
        scores=self.getscoredlist(rows,wordids)
        # sorted([(s,url),(s,url),...],reverse=1)
        rankedscores=sorted([(score,url) for (url,score) in scores.items()],reverse=1) 
        for (score,urlid) in rankedscores[0:10]:
           print '%f\t%s' % (score,self.geturlname(urlid))
        # add after nn
        return wordids,[r[1] for r in rankedscores[0:10]]

    def normalizescores(self,scores,smallIsBetter=0):
        vsmall=0.00001 # Avoid division by zero errors
        if smallIsBetter:
            minscore=min(scores.values( ))
            return dict([(u,float(minscore)/max(vsmall,l)) for (u,l) \
                in scores.items()]) 
        else:
            maxscore=max(scores.values( ))
            if maxscore==0: maxscore=vsmall
            return dict([(u,float(c)/maxscore) for (u,c) in scores.items()])
    
    def frequencyscore(self,rows):
        # init, (urlid, freq)
        counts=dict([(row[0],0) for row in rows])
        for row in rows: counts[row[0]]+=1
        return self.normalizescores(counts)

    
    def locationscore(self,rows):
        locations=dict([(row[0],1000000) for row in rows])
        for row in rows:
            loc=sum(row[1:])
            if loc<locations[row[0]]: locations[row[0]]=loc
        return self.normalizescores(locations,smallIsBetter=1)

    def distancescore(self,rows):
        # If there's only one word, everyone wins!
        if len(rows[0])<=2: return dict([(row[0],1.0) for row in rows])
        # Initialize the dictionary with large values
        mindistance=dict([(row[0],1000000) for row in rows])
        for row in rows:
            dist=sum([abs(row[i]-row[i-1]) for i in range(2,len(row))])
            if dist<mindistance[row[0]]: mindistance[row[0]]=dist
        return self.normalizescores(mindistance,smallIsBetter=1)

    def inboundlinkscore(self,rows):
        uniqueurls=set([row[0] for row in rows])
        inboundcount=dict([(u,self.con.execute( \
            'select count(*) from link where toid=%d' % u).fetchone()[0]) for u in uniqueurls])
        return self.normalizescores(inboundcount)

    def calculatepagerank(self,iterations=20):
        # clear out the current PageRank tables
        self.conn.execute('drop table if exists pagerank')
        self.conn.execute('create table pagerank(urlid primary key,score)')
        # initialize every url with a PageRank of 1
        self.conn.execute('insert into pagerank select rowid, 1.0 from urllist') 
        self.dbcommit( )
        for i in range(iterations):
            print "Iteration %d" % (i)
            for (urlid,) in self.conn.execute('select rowid from urllist'):
                pr=0.15
                # Loop through all the pages that link to this one
                for (linker,) in self.conn.execute('select distinct fromid from link where toid=%d' % urlid):
                    # Get the PageRank of the linker
                    linkingpr=self.conn.execute('select score from pagerank where urlid=%d' % linker).fetchone()[0]
                    # Get the total number of links from the linker 
                    linkingcount=self.con.execute('select count(*) from link where fromid=%d' % linker).fetchone()[0] 
                    pr+=0.85*(linkingpr/linkingcount)
                self.conn.execute('update pagerank set score=%f where urlid=%d' % (pr,urlid)) 
            self.dbcommit( )

    def pagerankscore(self,rows):
        pageranks=dict([(row[0],self.con.execute('select score from pagerank where urlid=%d' % row[0]).fetchone()[0]) for row in rows]) 
        maxrank=max(pageranks.values( ))
        normalizedscores=dict([(u,float(l)/maxrank) for (u,l) in pageranks.items()]) 
        return normalizedscores

    def linktextscore(self,rows,wordids):
        linkscores=dict([(row[0],0) for row in rows])
        for wordid in wordids:
            cur=self.con.execute('select link.fromid,link.toid from linkwords,link where wordid=%d and linkwords.linkid=link.rowid' % wordid)
            for (fromid,toid) in cur:
                if toid in linkscores:
                    pr=self.con.execute('select score from pagerank where urlid=%d' % fromid).fetchone()[0]
                    linkscores[toid]+=pr
        maxscore=max(linkscores.values( ))
        normalizedscores=dict([(u,float(l)/maxscore) for (u,l) in linkscores.items()]) 
        return normalizedscores


    import nn
    mynet=nn.searchnet('nn.db')

    def nnscore(self,rows,wordids):
        # Get unique URL IDs as an ordered list
        urlids=[urlid for urlid in set([row[0] for row in rows])]
        nnres=mynet.getresult(wordids,urlids)
        scores=dict([(urlids[i],nnres[i]) for i in range(len(urlids))])
        return self.normalizescores(scores)
