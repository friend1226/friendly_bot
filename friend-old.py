import asyncio, discord, time, gspread, re, datetime, random, requests, os, traceback, scoreCalc, decimal
from oauth2client.service_account import ServiceAccountCredentials as SAC
from collections import defaultdict
from bs4 import BeautifulSoup

scope = [
'https://spreadsheets.google.com/feeds',
'https://www.googleapis.com/auth/drive',
]
jsonfile = 'friend-266503-91ab7f0dce62.json'
credentials = SAC.from_json_keyfile_name(jsonfile, scope)
gs = gspread.authorize(credentials)
gs.login()
spreadsheet = "https://docs.google.com/spreadsheets/d/1SA2u-KgTsHcXcsGEbrcfqWugY7sgHIYJpPa5fxNEJYc/edit#gid=0"
doc = gs.open_by_url(spreadsheet)

worksheet = doc.worksheet('data')

app = discord.Client()

with open("key.txt", 'r') as f:
    token = f.read()

err = "WRONG COMMAND : "

url_base = "http://ops.dgsrz.com/profile.php?uid="
mapr = re.compile(r"(.*) [-] (.*) [(](.*)[)] [\[](.*)[]]")
playr = re.compile(r"(.*) / (.*) / (.*) / (.*)x / (.*)%")
missr = re.compile(r"[{]\"miss\":(\d+), \"hash\":.*[}]")

datas = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(dict))))
teams = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(dict))))
timers = dict()
ids = defaultdict(int)

restartalert = False

noticechannels = [651054921537421323, 652487382381363200]

getd = lambda n: decimal.Decimal(str(n))
neroscoreV2 = lambda maxscore, score, acc, miss: round((getd(score)/getd(maxscore) * 600000
                                                        + (getd(acc)**4)/250)
                                                       * (1-getd(0.003)*getd(miss)))
jetonetV2 = lambda maxscore, score, acc, miss: round(getd(score)/getd(maxscore) * 500000
                                                     + ((max(getd(acc) - 80, 0))/20)**2 * 500000)
osuV2 = lambda maxscore, score, acc, miss: round(getd(score)/getd(maxscore) * 700000
                                                 + (getd(acc)/100)**10 * 300000)

kind = ['number', 'artist', 'author', 'title', 'diff']
rmeta = r'\$(*+.?[^{|'

analyze = re.compile(r"(.*) [-] (.*) [(](.*)[)] [\[](.*)[]]")
def makefull(**kwargs):
    return f"{kwargs['artist']} - {kwargs['title']} ({kwargs['author']}) [{kwargs['diff']}]"

def dice(s):
    s = s.partition('d')
    if s[1]=='': return None
    return tuple(str(random.randint(1, int(s[2]))) for _ in range(int(s[0])))

def getrecent(id):
    url = url_base + str(id)
    html = requests.get(url)
    if html.status_code != 200:
        return
    bs = BeautifulSoup(html.text, "html.parser")
    recent = bs.select_one("#activity > ul > li:nth-child(1)")
    recentMapinfo = recent.select("a.clear > strong.block")[0].text
    recentPlayinfo = recent.select("a.clear > small")[0].text
    recentMiss = recent.select("#statics")[0].text
    return (mapr.match(recentMapinfo).groups(), playr.match(recentPlayinfo).groups(), missr.match(recentMiss).groups())

class Timer:
    def __init__(self, ch, name, seconds):
        self.channel = ch
        self.name = name
        self.seconds = seconds
        self.nowloop = asyncio.get_event_loop()
        self.starttime = datetime.datetime.utcnow()
        self.task = self.nowloop.create_task(self.run())
    
    async def run(self):
        await asyncio.sleep(self.seconds)
        await self.callback()
    
    async def callback(self):
        global timers
        await self.channel.send(f"Timer **{self.name}**: TIME OVER.")
        del timers[self.name]

    def left(self):
        return self.seconds - (datetime.datetime.utcnow()-self.starttime).total_seconds()


helptxt = discord.Embed(title="COMMANDS DESCRIPTHION",
                        description='**ver. 1.3_20200302**\n'
                                    '<neccesary parameter> (optional parameter) [multi-case parameter]',
                        color=discord.Colour(0xfefefe))
helptxt.add_field(name='f:hello', value='"Huy I\'m here XD"')
helptxt.add_field(name='f:say *<message>*', value='Say <message>.')
helptxt.add_field(name='f:dice *<dice1>* *(dice2)* *(dice3)* ...', value='Roll the dice(s).\n'
                                                                         'Dice input form is *<count>*d*<range>*\n'
                                                                         'ex) 1d100, 3d10\n'
                                                                         'Dice(s) with wrong form will be ignored.')
helptxt.add_field(name='f:timer *(name)* *<second>*', value='Set timer. '
                                                            'You can omit *name*, then the bot will name it as number. '
                                                            '(start from 0)')
helptxt.add_field(name='f:timernow *<name>*', value='See how much time is left.')
helptxt.add_field(name='f:match __team <[add/remove]>__ *<team name>*', value='Add/remove team.')
helptxt.add_field(name='f:match __player <[add/remove]>__ *<team name>*', value='Add/remove **you (not another user)** to/from team.')
helptxt.add_field(name='f:match __score <[add/remove]>__ *<score>* *<acc>* *<miss>*', value='Add/remove score to/from **your** team; if you already added score, it\'ll chandge to new one; the parameter *(score)* can be left out when \'remov\'ing the score.')
helptxt.add_field(name='f:match __submit__', value='Sum scores of each team and give setscore(+1) to the winner team(s); **If there\'s tie, all teams of tie will get a point**.')
helptxt.add_field(name='f:match __now__', value='Show how many scores each team got.')
helptxt.add_field(name='f:match __end__', value='Compare setscores of each team and show who\'s the winner team(s).')
helptxt.add_field(name='f:match __reset__', value='DELETE the current match')
helptxt.add_field(name='f:match __setmap__ *<[kind]>*', value='Set a map of current play\n'
                                                      'f:setmap **infos** _<artist>_**::**_<title>_**::**_<author>_**::**_<difficult>_\n'
                                                      'f:setmap **full** *<artist>* - *<title>* (*<author>**) [*<difficult>*]\n'
                                                      'f:setmap **score** *<autoScore>*\n'
                                                      'f:setmap _**<mapNickname>**_\n\n'
                                                      'If you want to submit with scoreV2, you need to set autoscore '
                                                      'by using "f:setmap score" or "f:setmap _mapNickname_".')

@app.event
async def on_ready():
    print(f"[{time.strftime('%Y-%m-%d %a %X', time.localtime(time.time()))}]")
    print("BOT NAME :", app.user.name)
    print("BOT ID   :", app.user.id)
    game = discord.Game("f:help")
    await app.change_presence(status=discord.Status.online, activity=game)
    print("==========BOT START==========")

@app.event
async def on_message(message):
    ch = message.channel
    msgtime = message.created_at
    nowtime = datetime.datetime.utcnow()
    ping = f"{(nowtime-msgtime).total_seconds() * 1000 :.4f}"
    if credentials.access_token_expired:
        gs.login()
    try:
        global datas, teams, timers
        p = message.author
        pid = p.id
        g = message.guild.id
        chid = ch.id
        if pid == app.user.id:
            return None
        if message.content.startswith("f:"):
            print(f"[{time.strftime('%Y-%m-%d %a %X', time.localtime(time.time()))} ({ping}ms)] [{message.guild.name};{ch.name}] <{p.name};{pid}> {message.content}")
            command = message.content[2:].split(' ')


            if command[0]=="hello":
                await ch.send("Huy I'm here XD")
            
            elif command[0]=="ping":
                await ch.send(f"**Pong!**\n`{ping}ms`")

            elif command[0]=="help":
                await ch.send(embed=helptxt)


            elif command[0]=="dice":
                dices = command[1:]
                sendtxt = []
                for d in dices:
                    x = dice(d)
                    if x==None:
                        continue
                    sendtxt.append(f"__{d}__: **{' / '.join(x)}**")
                await ch.send(embed=discord.Embed(title="Dice Roll Result", description='\n'.join(sendtxt)))
            

            elif command[0]=="match":
                nowmatch = datas[g][chid]
                nowteams = teams[g][chid]

                if command[1]=="team":
                    teamname = ' '.join(command[3:])
                    if command[2]=="add":
                        if not nowmatch["setscores"][teamname] or nowmatch["scores"][teamname]:
                            nowmatch["setscores"][teamname] = 0
                            nowmatch["scores"][teamname] = dict()
                            await ch.send(embed=discord.Embed(title=f"Added Team \"{teamname}\".", description=f"Now team list:\n{chr(10).join(nowmatch['scores'].keys())}", color=discord.Colour.blue()))
                        else:
                            await ch.send(embed=discord.Embed(title=f"Team \"{teamname}\" already exists.", description=f"Now team list:\n{chr(10).join(nowmatch['scores'].keys())}", color=discord.Colour.blue()))
                    elif command[2]=="remove":
                        if len(nowmatch["scores"][teamname])==0:
                            del nowmatch["setscores"][teamname]
                            del nowmatch["scores"][teamname]
                            await ch.send(embed=discord.Embed(title=f"Removed Team \"{teamname}\"", description=f"Now team list:\n{chr(10).join(nowmatch['scores'].keys())}", color=discord.Colour.blue()))
                        else:
                            await ch.send(embed=discord.Embed(title=f"Can't be removed Team \"{teamname}\" because there's some members in the team.", description=f"Now team list:\n{chr(10).join(nowmatch['scores'].keys())}", color=discord.Colour.blue()))
                    else:
                        await ch.send(err+command[2])
                
                elif command[1]=="player":
                    teamname = ' '.join(command[3:])
                    if command[2]=="add":
                        if not nowteams[pid]:
                            nowteams[pid] = teamname
                            nowmatch["scores"][nowteams[pid]][pid] = (0,0,0)
                            await ch.send(embed=discord.Embed(
                                title=f"Added Player \"{p.name}\" to Team \"{teamname}\"",
                                description=f"Now Team {teamname} list:\n{chr(10).join(app.get_user(pl).name for pl in nowmatch['scores'][nowteams[pid]].keys())}",
                                color=discord.Colour.blue()))
                        else:
                            await ch.send(embed=discord.Embed(
                                title=f"Player \"{p.name}\" is already in a team!",
                                description=f"You already participated in Team {nowteams[pid]}. "
                                            f"If you want to change the team please command 'f:match player remove {nowteams[pid]}'."))
                    elif command[2]=="remove":
                        temp = nowteams[pid]
                        del nowteams[pid]
                        del nowmatch["scores"][temp][pid]
                        await ch.send(embed=discord.Embed(
                            title=f"Removed Player \"{p.name}\" to Team \"{teamname}\"",
                            description=f"Now Team {teamname} list:\n{chr(10).join(app.get_user(pl).name for pl in nowmatch['scores'][temp].keys())}",
                            color=discord.Colour.blue()))
                    elif command[2]=="forceadd":
                        if p.id != 327835849142173696:
                            await ch.send("ACCESS DENIED")
                            return
                        teamname = ' '.join(teamname.split(' ')[:-1])
                        p = app.get_user(int(command[-1]))
                        pid = p.id
                        if not nowteams[pid]:
                            nowteams[pid] = teamname
                            nowmatch["scores"][nowteams[pid]][pid] = (0,0,0)
                            await ch.send(embed=discord.Embed(
                                title=f"Added Player \"{p.name}\" to Team \"{teamname}\"",
                                description=f"Now Team {teamname} list:\n{chr(10).join(app.get_user(pl).name for pl in nowmatch['scores'][nowteams[pid]].keys())}",
                                color=discord.Colour.blue()))
                        else:
                            await ch.send(embed=discord.Embed(
                                title=f"Player \"{p.name}\" is already in a team!",
                                description=f"You already participated in Team {nowteams[pid]}. "
                                            f"If you want to change the team please command 'f:match player remove {nowteams[pid]}'."))
                    elif command[2]=="forceremove":
                        if p.id != 327835849142173696:
                            await ch.send("ACCESS DENIED")
                            return
                        teamname = ' '.join(teamname.split(' ')[:-1])
                        p = app.get_user(int(command[-1]))
                        pid = p.id
                        temp = nowteams[pid]
                        del nowteams[pid]
                        del nowmatch["scores"][temp][pid]
                        await ch.send(embed=discord.Embed(
                            title=f"Removed Player \"{p.name}\" to Team \"{teamname}\"",
                            description=f"Now Team {teamname} list:\n{chr(10).join(app.get_user(pl).name for pl in nowmatch['scores'][temp].keys())}",
                            color=discord.Colour.blue()))
                    else:
                        await ch.send(err+command[2])

                elif command[1]=="score":
                    if command[2]=="add":
                        nowmatch["scores"][nowteams[pid]][pid] = tuple(map(float, command[3:6]))
                        await ch.send(embed=discord.Embed(title=f"Added/changed {p.name}'(s) score", description=f"{command[3]} to Team {nowteams[pid]}", color=discord.Colour.blue()))
                    elif command[2]=="remove":
                        temp = nowmatch["scores"][nowteams[pid]][pid]
                        nowmatch["scores"][nowteams[pid]][pid] = (0,0,0)
                        await ch.send(embed=discord.Embed(title=f"Removed {p.name}'(s) score", description=f"{temp} from Team {nowteams[pid]}", color=discord.Colour.blue()))
                    elif command[2]=="forceadd":
                        if p.id != 327835849142173696:
                            await ch.send("ACCESS DENIED")
                            return
                        p = app.get_user(int(command[-1]))
                        pid = p.id
                        nowmatch["scores"][nowteams[pid]][pid] = tuple(map(float, command[3:6]))
                        await ch.send(embed=discord.Embed(title=f"Added/changed {p.name}'(s) score", description=f"{command[3]} to Team {nowteams[pid]}", color=discord.Colour.blue()))
                    elif command[2]=="forceremove":
                        if p.id != 327835849142173696:
                            await ch.send("ACCESS DENIED")
                            return
                        p = app.get_user(int(command[-1]))
                        pid = p.id
                        temp = nowmatch["scores"][nowteams[pid]][pid]
                        nowmatch["scores"][nowteams[pid]][pid] = (0,0,0)
                        await ch.send(embed=discord.Embed(title=f"Removed {p.name}'(s) score", description=f"{temp} from Team {nowteams[pid]}", color=discord.Colour.blue()))
                    else:
                        await ch.send(err+command[2])
                
                elif command[1]=="setmap":
                    done = True
                    if command[2]=="infos":
                        nowmatch["map"]["artist"], nowmatch["map"]["title"], nowmatch["map"]["author"], nowmatch["map"]["diff"] = ' '.join(command[3:]).split('::')
                    elif command[2]=="full":
                        nowmatch["map"]["artist"], nowmatch["map"]["title"], nowmatch["map"]["author"], nowmatch["map"]["diff"] = analyze.match(' '.join(command[3:])).groups()
                    elif command[2]=="score":
                        nowmatch["map"]["sss"] = int(command[3])
                    elif command[2]=="scoreauto":
                        s = scoreCalc.scoreCalc(' '.join(command[3:]))
                        nowmatch["map"]["sss"] = s.getAutoScore()
                        s.close()
                    else:
                        c = worksheet.findall(command[2])
                        if c != []:
                            c = c[0]
                            nowmatch["map"]["author"], nowmatch["map"]["artist"], nowmatch["map"]["title"], nowmatch["map"]["diff"], nowmatch["map"]["sss"] = tuple(worksheet.cell(c.row, i+1).value for i in range(5))
                            nowmatch["map"]["mode"] = command[2]
                        else:
                            await ch.send(f"NOT FOUND: {command[2]}")
                            done = False
                    if done:
                        await ch.send(f'DONE: {makefull(**nowmatch["map"])}')

                elif command[1]=="bind":
                    ids[pid] = int(command[2])
                    await ch.send(embed=discord.Embed(title=f'DONE: {app.get_user(pid).name} binded to {command[2]}',
                                                      color=discord.Colour(0xfefefe)))

                elif command[1]=="setform":
                    form = ' '.join(command[2:])
                    temp = []
                    for k in kind:
                        t = len(re.findall(k, form))
                        if t == 1:
                            temp.append(k)
                        elif t:
                            await ch.send("<!> There should not be the same arguments.")
                            return
                    for c in rmeta:
                        form = form.replace(c, '\\'+c)
                    for t in temp:
                        form = form.replace(t, '(?P<'+t+'>.*?)')
                    nowmatch["form"] = [re.compile(form), temp]
                    await ch.send(f"Form set: {form}")

                elif command[1]=="autosubmit":
                    if len(command)==2:
                        check = []
                        mode = ''
                    else:
                        check = list(map(int, command[2:-1]))
                        mode = command[-1]
                    done = []
                    for t in nowmatch["scores"]:
                        for p in nowmatch["scores"][t]:
                            if ids[p]:
                                recent = getrecent(ids[p])
                                if not recent:
                                    continue
                                mapartist, maptitle, mapauthor, mapdiff = recent[0]
                                score = int(recent[1][1].replace(',', ''))
                                acc = float(recent[1][4])
                                miss = float(recent[2][0])
                                modes = set(recent[1][2].split(', '))
                                if type(nowmatch["form"]) != defaultdict:
                                    check = [0, 0, 0, 0]
                                    d = nowmatch["form"][0].match(mapdiff)
                                    if not d:
                                        continue
                                    for tt in nowmatch["form"][1]:
                                        if tt == "artist":
                                            check[0] = 1
                                            mapartist = d.group(tt)
                                        elif tt == "title":
                                            check[1] = 1
                                            maptitle = d.group(tt)
                                        elif tt == "author":
                                            check[2] = 1
                                            mapauthor = d.group(tt)
                                        elif tt == "diff":
                                            check[3] = 1
                                            mapdiff = d.group(tt)
                                        elif tt == "number":
                                            mode = d.group("number")
                                            if mode != nowmatch['map']['mode'].partition(';')[2]:
                                                continue
                                if len(check):
                                    if check[0]:
                                        if mapartist != nowmatch["map"]["artist"]:
                                            continue
                                    if check[1]:
                                        if maptitle != nowmatch["map"]["title"]:
                                            continue
                                    if check[2]:
                                        if mapauthor != nowmatch["map"]["author"]:
                                            continue
                                    if check[3]:
                                        if mapdiff != nowmatch["map"]["diff"]:
                                            continue
                                modes -= {'NoFail'}
                                if not mode:
                                    pass
                                elif mode=='HD':
                                    if modes == {'Hidden'}:
                                        pass
                                    else:
                                        continue
                                elif mode=='HR':
                                    if modes == {'HardRock'}:
                                        pass
                                    else:
                                        continue
                                elif mode=='DT':
                                    if modes == {'DoubleTime'}:
                                        pass
                                    elif modes == {'Hidden', 'DoubleTime'}:
                                        score /= 1.06
                                elif mode=='NM':
                                    if modes != {'None'}:
                                        continue
                                elif mode=='FM':
                                    if modes - {'DoubleTime'} != modes:
                                        continue
                                done.append(p)
                                nowmatch["scores"][nowteams[p]][p] = (score, acc, miss)
                    sendtxt = "**The player's scores here had been add automatically:**\n"
                    for p in done:
                        sendtxt += "__"
                        sendtxt += app.get_user(p).name
                        sendtxt += "__ : "
                        info = nowmatch["scores"][nowteams[p]][p]
                        sendtxt += f"{info[0]} score, {info[1]}% accuracy, {int(info[2])} miss(es)\n"
                    sendtxt += "\nIf your score haven't be added automatically, " \
                               "you might played different map or with different modes\n" \
                               "OR you didn't binded your UID with yourself.\n" \
                               "Use `f:match bind UID` to bind.\n" \
                               "If you want to upload manually, use `f:match score add`.\n" \
                               "(If you played with HDDT in DT map, presented score is divided by 1.06.)"
                    await ch.send(embed=discord.Embed(title="Finished", description=sendtxt))

                elif command[1]=="submit":
                    scores = dict()
                    sums = dict()
                    if len(command)>2:
                        if command[2]=="nero2":
                            if nowmatch["map"]["sss"]:
                                for t in nowmatch["scores"]:
                                    scores[t] = dict()
                                    sums[t] = 0
                                    for p in nowmatch["scores"][t]:
                                        v = neroscoreV2(int(nowmatch["map"]["sss"]), *nowmatch["scores"][t][p])
                                        scores[t][p] = v
                                        sums[t] += v
                            else:
                                await ch.send("You have to set map with auto score.")
                                return
                        elif command[2]=="jet2":
                            if nowmatch["map"]["sss"]:
                                for t in nowmatch["scores"]:
                                    scores[t] = dict()
                                    sums[t] = 0
                                    for p in nowmatch["scores"][t]:
                                        v = jetonetV2(int(nowmatch["map"]["sss"]), *nowmatch["scores"][t][p])
                                        scores[t][p] = v
                                        sums[t] += v
                            else:
                                await ch.send("You have to set map with auto score.")
                                return
                    else:
                        for t in nowmatch["scores"]:
                            scores[t] = dict()
                            sums[t] = 0
                            for p in nowmatch["scores"][t]:
                                v = nowmatch["scores"][t][p][0]
                                scores[t][p] = v
                                sums[t] += v
                            
                    winners = list(filter(lambda x: sums[x]==max(sums.values()), sums.keys()))
                    mapinfo = "Map: " + makefull(**nowmatch["map"])
                    for w in winners:
                        nowmatch["setscores"][w] += 1
                    desc = mapinfo+"\n\n"+\
                           '\n\n'.join(f"__TEAM {i}__: **{sums[i]}**\n"+
                                       ('\n'.join(f"{app.get_user(j).name}: {scores[i][j]}" for j in scores[i]))
                                       for i in sums)
                    sendtxt = discord.Embed(title=f"__**Team {', '.join(winners)} take(s) a point!**__",
                                            description=desc,
                                            color=discord.Colour.red())
                    sendtxt.add_field(name=f"\nNow match points:",
                                      value='\n'.join(f"__TEAM {i}__: **{nowmatch['setscores'][i]}**" for i in sums))
                    await ch.send(embed=sendtxt)
                    for t in sums:
                        for p in nowmatch["scores"][t]:
                            nowmatch["scores"][t][p] = (0,0,0)
                    nowmatch["map"] = dict()
                    await ch.send(embed=discord.Embed(title="Successfully reset round", color=discord.Colour.red()))
                
                elif command[1]=="now":
                    desc = ''
                    for i in nowmatch["setscores"]:
                        desc += f"__TEAM {i}__: **{nowmatch['setscores'][i]}**\n"
                        for p in nowmatch["scores"][i]:
                            desc += app.get_user(p).name + '\n'
                        desc += '\n'
                    await ch.send(embed=discord.Embed(
                        title="Current match progress", description=desc.rstrip(), color=discord.Colour.orange()))

                elif command[1]=="end":
                    sums = sorted(list(nowmatch["setscores"].items()), key=lambda x: x[1], reverse=True)
                    tl = []
                    tt = "__**MATCH END**__"
                    for i, t in enumerate(sums):
                        temp = ''
                        if (i+1)%10==1:
                            temp += f"{i+1}st"
                        elif (i+1)%10==2:
                            temp += f"{i+1}nd"
                        elif (i+1)%10==3:
                            temp += f"{i+1}rd"
                        else:
                            temp += f"{i+1}th"
                        tl.append(temp+f" TEAM : {t[0]} <== {t[1]} score(s)")
                    sendtxt = discord.Embed(title=tt,
                                            description='\n'.join(tl)+f"\n\n__**TEAM {sums[0][0]}, YOU ARE WINNER!\n"
                                                                      f"CONGRATURATIONS!!!**__",
                                            color=discord.Colour.gold())
                    await ch.send(embed=sendtxt)
                
                elif command[1]=="reset":
                    nowmatch = dict()
                    nowteams = dict()
                    await ch.send(embed=discord.Embed(title="Successfully reset.", color=discord.Colour(0x808080)))
                
                else:
                    await ch.send(err+command[1])
                
                datas[g][chid] = nowmatch
                teams[g][chid] = nowteams
            
            
            elif command[0]=="timer":
                if len(command)==2:
                    i = 0
                    while 1:
                        if not (str(i) in timers):
                            break
                        i += 1
                    name = str(i)
                    sec = int(command[1])
                    timers[name] = Timer(ch, name, sec)
                    await ch.send(f"Timer **{name}** set. ({sec}s)")
                else:
                    name, sec = ' '.join(command[1:-1]), int(command[-1])
                    if name in timers:
                        await ch.send("Already running")
                    else:
                        timers[name] = Timer(ch, name, sec)
                        await ch.send(f"Timer **{name}** set. ({sec}s)")

            elif command[0]=="timernow":
                name = command[1]
                if name in timers:
                    await ch.send(f"Timer {name}: {timers[name].left() :.3f}s left.")
                else:
                    await ch.send(f"No timer named {name}!")

            elif command[0]=="say":
                sendtxt = " ".join(command[1:])
                if not message.mention_everyone:
                    for u in message.mentions:
                        sendtxt = sendtxt.replace("<@!"+str(u.id)+">", "*"+u.name+"*")
                    if sendtxt!="":
                        print("QUERY:", sendtxt)
                        await ch.send(sendtxt)
                    else:
                        await ch.send("EMPTY")
                else:
                    await ch.send("DO NOT MENTION EVERYONE OR HERE")
            
            
            elif command[0]=="sayresult":
                if p.id == 327835849142173696:
                    await ch.send(eval(' '.join(command[1:])))
                else:
                    await ch.send("ACCESS DENIED")
            
            elif command[0]=="ns2":
                await ch.send(f"__{p.name}__'(s) NeroScoreV2 result = __**{neroscoreV2(*map(float, command[1:]))}**__")

            elif command[0]=="jt2":
                await ch.send(f"__{p.name}__'(s) JetonetV2 result = __**{jetonetV2(*map(float, command[1:]))}**__")

            elif command[0]=="osu2":
                await ch.send(f"__{p.name}__'(s) osuV2 result = __**{osuV2(*map(float, command[1:]))}**__")
            
            elif command[0]=="run":
                if p.id == 327835849142173696:
                    exec(' '.join(command[1:]), globals(), locals())
                    await ch.send("RAN COMMAND(S)")
                else:
                    await ch.send("ACCESS DENIED")

            elif command[0]=="asyncrun":
                if p.id == 327835849142173696:
                    exec('async def __do():\n ' + '\n '.join(' '.join(command[1:]).split('\n')), dict(locals(), **globals()), locals())
                    await locals()['__do']()
                    await ch.send('RAN COMMAND(S)')
                else:
                    await ch.send("ACCESS DENIED")
            
            else:
                await ch.send(err+command[0])

    
    except Exception as ex:
        await ch.send(f"ERROR OCCURED: {ex}")
        print(traceback.format_exc())



loop = asyncio.get_event_loop()
try:
    loop.run_until_complete(app.start(token))
except KeyboardInterrupt:
    print("\nForce stop")
except BaseException as ex:
    print(repr(ex))
    print(ex)
finally:
    loop.run_until_complete(app.logout())
    loop.run_until_complete(loop.shutdown_asyncgens())
    loop.run_until_complete(asyncio.sleep(1))
    loop.close()