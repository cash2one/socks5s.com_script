#!/usr/bin/env python
# coding=utf-8

import time
from random import random
import hashlib
import sys
import commands
import json
import logging  
from optparse import OptionParser

from models import *


cardpass = {}
global mysql
mysql = MySQLHander()

logging.basicConfig(level=logging.DEBUG,  
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',  
                    datefmt='%Y/%m/%d %H:%M:%S'
                    )

logger = logging.getLogger(__name__)

def shell_exec(cmd):
    return commands.getstatusoutput(cmd)


#拷贝到集群
def scp(filename):
    sql = "select hostip from s_host where zone='{0}'".format(options.zone)
    mysql.query(sql)
    hosts = mysql.fetchAllRows()
    for host in hosts:
        # import ipdb;ipdb.set_trace()
        path = options.rpath
        cmd = "scp {0} fengxuan@{1}:{2}/".format(filename, host[0], path)
        (status, output) = shell_exec(cmd)
        logger.info("upload file {0} to dir {1}".format(filename, path))

        # import ipdb;ipdb.set_trace()
        cmd = "touch {0}.SUCCESS &&scp {0}.SUCCESS fengxuan@{1}:{2}".format(filename, host[0], path)
        (status, output) = shell_exec(cmd)
        print output
        if status == 0:
            logger.info("host {0} upload ok !".format(host[0]))
    logger.info("scp ok!")
    os.remove(filename)
    os.remove("{0}.SUCCESS".format(filename))



#生成ss账号密码
def generatepass(number):
    global cardpass
    m2 = hashlib.md5()
    sql = "select max(port) from s_ssaccount"
    mysql.query(sql)
    start = mysql.fetchOneRow()
    if start[0] == None:
        start = 10000
    else:
        start = int(start[0]) + 1
    for num in xrange(start, start + number):
        m2.update("{0}{1}".format(time.time(), random()))
        cardpass[num] = m2.hexdigest()
        print num
    insertdb(cardpass)
    scp(JsonParse(cardpass))


def JsonParse(cardpass, mode="gen"):
    if mode == "gen":
        filename = "pass_{0}.json".format(int(time.time()))
    elif mode == "update":
        filename = "update_{0}.json".format(int(time.time()))
    elif mode == "stop":
        filename = "stop_{0}.json".format(int(time.time()))
    elif mode == "rechange":
        filename = "rechange_{0}.json".format(int(time.time()))
    fp = open(filename, 'wb')
    source = json.dumps(cardpass, indent=4)
    fp.write(source)
    fp.close()
    return filename


def insertdb(cardpass):
    for card in cardpass:
        sql = "insert into s_ssaccount(`port`, `pass`) values({0}, '{1}')".format(card, cardpass[card])
        mysql.insert(sql)
    logger.info("insert db ok!")


#如果用户的流量超过，停止用户访问
def stopUser():
    logger.info("start stoping check")
    sql = "select id,port from s_user where streamcount < 0"
    mysql.query(sql)
    users = mysql.fetchAllRows()
    if len(users) == 0:
        return None
    portlist = []
    for user in users:
        sql = "update s_user set streamcount=0,port=0,sspass='' where id={0}".format(user[0])
        mysql.update(sql)
        portlist.append(user[1])
    logger.info("uploading stop file...")
    scp(JsonParse(portlist, 'stop'))
    logger.info("stoped ok!")


#每天将付费用户的使用天数-1
def reducetime():
    sql = "select buytime,port,id from s_user where buytime > 0"
    mysql.query(sql)
    vip = mysql.fetchAllRows()
    for v in vip:
        sql = "update s_user set buytime={0} where id={1}".format(int(v[0]) -1, v[2])
        mysql.update(sql)
        if int(v[0]) == 1:
            deleteUser({'port':v[1], 'id':v[2]})
    logger.info("reducetime ok!")


#将用户的ss账号的密码置空, s_ssaccount账号将状态置为0，密码修改
def deleteUser(info):
    m2 = hashlib.md5()
    m2.update("{0}{1}".format(time.time(), random()))
    newpass = m2.hexdigest()
    sql = "update s_ssaccount set pass='{0}',status=0 where port={1}".format(newpass, info['port'])
    mysql.update(sql)
    sql = "update s_user set port=0,sspass='' where id={0}".format(info['id'])
    mysql.update(sql)
    updateportpass = {info['port']:newpass}
    filename = JsonParse(updateportpass, 'update')
    logger.info("uploading update file...")
    scp(filename)
    logger.info("deleteUser ok!")


def async(port):
    sql = "select pass from s_ssaccount where port={0}".format(port)
    mysql.query(sql)
    result = mysql.fetchOneRow()
    # import ipdb;ipdb.set_trace()
    if result is None:
        logger.critical('No such pass or port!')
        return False
    rechange = {port:result[0]}
    filename = JsonParse(rechange, 'update')
    logger.info("uploading rechange file...")
    scp(filename)
    logger.info("upload rechange file ok!")



def usage():
    parser=OptionParser()
    parser.add_option("-m", "--mode", type="string", dest="mode", help="Runmode Synchronous or Asynchronous")
    parser.add_option("-n", "--number", type="int", dest="number", help="Runmode Synchronous or Asynchronous")
    parser.add_option("-z", "--zone", type="string", dest="zone", help="host zone ", default="fuck01")
    parser.add_option("-p", "--port", type="string", dest="port", help="the port to update")
    parser.add_option("-r", "--rpath", type="string", dest="rpath", help="remotepath to upload json", default="/home/fengxuan/updatejson/")
    if len(sys.argv) < 2:
        parser.print_help()
        sys.exit()
    global options
    (options, args) = parser.parse_args()

def main():
    usage()
    if options.mode == 'generate':
        generatepass(options.number)
    elif options.mode == 'daily':
        reducetime()
        stopUser()
    elif options.mode == 'async':
        async(options.port)

if __name__ == '__main__':
    #python reduce.py -z fuck01 -m generate -n 10 #生成10个ss账号
    #python reduce.py -z fuck01 -m daily 每天巡检任务
    #python reduce.py -z fuck01 -m async -p 10002 每天巡检任务
    main()
    mysql.close()
