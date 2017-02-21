# -*- coding: UTF-8 -*-

from math import tanh
import sqlite3
from pysqlite2 import dbapi2 as sqlite

def dtanh(y):
    return 1.0-y*y

class searchnet:
    def __init__(self,dbname):
        self.con=sqlite.connect(dbname)
    
    def __del__(self): self.con.close( )
    
    #仅有一个隐藏层的网络，没想到结构倒是异常的简单
    def maketables(self):
        self.con.execute('create table hiddennode(create_key)') 
        self.con.execute('create table wordhidden(fromid,toid,strength)') 
        self.con.execute('create table hiddenurl(fromid,toid,strength)') 
        self.con.commit()

    # layer 0 输入层；layer 1 输出层，获取from-to的强度，其实就是各个输入值的权重
    def getstrength(self,fromid,toid,layer):
        if layer==0: table='wordhidden'
        else: table='hiddenurl'
        res=self.con.execute('select strength from %s where fromid=%d and toid=%d' % 
            (table,fromid,toid)).fetchone() 
        if res==None:
            if layer==0: return -0.2 # 输入层默认强度 -0.2
            if layer==1: return 0    # 输出层默认强度 0
        return res[0]
    
    # 设置强度
    def setstrength(self,fromid,toid,layer,strength):
        if layer==0: table='wordhidden'
        else: table='hiddenurl'
        res=self.con.execute('select rowid from %s where fromid=%d and toid=%d' % 
            (table,fromid,toid)).fetchone() 
        if res==None:
            self.con.execute('insert into %s (fromid,toid,strength) values (%d,%d,%f)' %
                (table,fromid,toid,strength))
        else:
            rowid=res[0]
            self.con.execute('update %s set strength=%f where rowid=%d' %
                (table,strength,rowid))

    # 生成隐藏层的节点
    def generatehiddennode(self,wordids,urls):
        if len(wordids)>3: return None
        # Check if we already created a node for this set of words,排序的
        createkey='_'.join(sorted([str(wi) for wi in wordids])) 
        res=self.con.execute("select rowid from hiddennode where create_key='%s'" % createkey).fetchone()
        # If not, create it
        if res==None:
            cur=self.con.execute(
                "insert into hiddennode (create_key) values ('%s')" % createkey)
            hiddenid=cur.lastrowid
            # Put in some default weights，设置输入层的强度 1.0/len of wordids
            for wordid in wordids:
                self.setstrength(wordid,hiddenid,0,1.0/len(wordids))
            for urlid in urls:
                # 设置输出层的强度, 0.1
                self.setstrength(hiddenid,urlid,1,0.1) 
            self.con.commit()
    
    def getallhiddenids(self,wordids,urlids):
        l1={}
        # 从输入层来获取所有对应的隐藏节点
        for wordid in wordids:
            cur=self.con.execute(
                'select toid from wordhidden where fromid=%d' % wordid)
            for row in cur: l1[row[0]]=1 #记录隐藏节点
        # 从输出层来获取所有对应的隐藏节点
        for urlid in urlids:
            cur=self.con.execute(
                'select fromid from hiddenurl where toid=%d' % urlid)
            for row in cur: l1[row[0]]=1
        return l1.keys()

    # 设置网络，并从数据库中获取权重信息（有记忆）
    def setupnetwork(self,wordids,urlids):
        # value lists
        self.wordids=wordids
        # 获取所有关联的隐藏节点,是按照输入和输出获取的并集
        self.hiddenids=self.getallhiddenids(wordids,urlids)
        self.urlids=urlids
        # node outputs
        self.ai = [1.0]*len(self.wordids)   # 输入
        self.ah = [1.0]*len(self.hiddenids) # 隐藏
        self.ao = [1.0]*len(self.urlids)    # 输出
        # create weights matrix，组织输入权重矩阵，有些权重是不存在的，hiddenid是按输入层和输出层获取的并集
        # word -> hidden
        self.wi = [[self.getstrength(wordid,hiddenid,0)
                    for hiddenid in self.hiddenids]
                    for wordid in self.wordids]
        print(self.wi) 
        # 输出的权重矩阵
        # hidden -> url          
        self.wo = [[self.getstrength(hiddenid,urlid,1)
                    for urlid in self.urlids]
                    for hiddenid in self.hiddenids]
        print(self.wo)

    def feedforward(self):
        # the only inputs are the query words
        for i in range(len(self.wordids)):
            self.ai[i] = 1.0 # 为啥都是1，而且上文已经设置过了
        # hidden activations, 按每一个hidden节点进行计算，f(x)=w*x
        for j in range(len(self.hiddenids)):
            sum = 0.0
            for i in range(len(self.wordids)):
                sum = sum + self.ai[i] * self.wi[i][j] # 每一个word到hidden的权重
            self.ah[j] = tanh(sum) # activation function calc
        # output activations
        for k in range(len(self.urlids)):
            sum = 0.0
            for j in range(len(self.hiddenids)):
                sum = sum + self.ah[j] * self.wo[j][k]
            self.ao[k] = tanh(sum)
        return self.ao[:]
    
    def getresult(self,wordids,urlids): 
        self.setupnetwork(wordids,urlids) 
        return self.feedforward()

    # 训练，反向传播，最终目标调整权重值
    # TODO 对于反向传播算法的数学理解还要深入，参考知乎上的知识（不是难，而是知识体系有缺失）
    def backPropagate(self, targets, N=0.5):
        # calculate errors for output，输出误差
        output_deltas = [0.0] * len(self.urlids)
        for k in range(len(self.urlids)):
            error = targets[k]-self.ao[k]
            output_deltas[k] = dtanh(self.ao[k]) * error
        # calculate errors for hidden layer
        hidden_deltas = [0.0] * len(self.hiddenids)
        for j in range(len(self.hiddenids)):
            error = 0.0
            # ~>
            for k in range(len(self.urlids)):
                error = error + output_deltas[k]*self.wo[j][k]
            # <~
            hidden_deltas[j] = dtanh(self.ah[j]) * error
        # update output weights
        for j in range(len(self.hiddenids)):
            for k in range(len(self.urlids)):
                change = output_deltas[k]*self.ah[j]
                self.wo[j][k] = self.wo[j][k] + N*change
        # update input weights
        for i in range(len(self.wordids)):
            for j in range(len(self.hiddenids)):
                change = hidden_deltas[j]*self.ai[i]
                self.wi[i][j] = self.wi[i][j] + N*change
    
    def trainquery(self,wordids,urlids,selectedurl):
        # generate a hidden node if necessary
        self.generatehiddennode(wordids,urlids)
        self.setupnetwork(wordids,urlids) 
        self.feedforward() 
        targets=[0.0]*len(urlids) 
        targets[urlids.index(selectedurl)]=1.0 # 预期的结果
        error = self.backPropagate(targets) 
        self.updatedatabase()
    
    def updatedatabase(self):
        # set them to database values
        for i in range(len(self.wordids)):
            for j in range(len(self.hiddenids)):
                self.setstrength(self.wordids[i],self. hiddenids[j],0,self.wi[i][j])
        for j in range(len(self.hiddenids)):
            for k in range(len(self.urlids)):
                self.setstrength(self.hiddenids[j],self.urlids[k],1,self.wo[j][k]) 
        self.con.commit()
