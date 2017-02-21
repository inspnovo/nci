import feedparser
import re
import sys

#for fix error: UnicodeEncodeError: 'ascii' codec can't encode characters in position 21-23: ordinal not in range(128)
reload(sys)
sys.setdefaultencoding( "utf-8" )

def genwordcounts(url):
    #
    d=feedparser.parse(url)
    wc={}

    #
    for e in d.entries:
        if 'summary' in e: summary=e.summary
        else: summary=e.description

        #
        words=getwords(e.title+' '+summary)
        for word in words:
            wc.setdefault(word,0)
            wc[word]+=1

    return d.feed.title,wc

def getwords(html):
    # 
    txt=re.compile(r'<[^>]+>').sub('',html)

    #
    words=re.compile(r'[^a-z^A-Z]+').split(txt)

    return [word.lower() for word in words if words!='']


apcount={}
wordcounts={}
feedlist=[line for line in file('feedlist.txt')]
for feedurl in feedlist:
    title,wc=genwordcounts(feedurl)
    wordcounts[title]=wc
    for word,count in wc.items():
        #notice, emergency times
        apcount.setdefault(word,0)
        if count>1:
            apcount[word]+=1

wordlist=[]
ignorelist=[]
for w,bc in apcount.items():
    frac=float(bc)/len(feedlist)
    if w not in ignorelist and frac>0.1 and frac<0.5: wordlist.append(w)

out=file('blogdata.txt','w')
out.write('Blog')
for word in wordlist: out.write('\t%s' % word)
out.write('\n')
for blog,wc in wordcounts.items():
    out.write(blog)
    #print(blog)
    print(len(wordlist))
    for word in wordlist:
        #print(word)
        if word in wc:
            #print(wc[word]) 
            out.write('\t%s' % wc[word])
        else: 
            out.write('\t0')
    out.write('\n')

out.flush
out.close
