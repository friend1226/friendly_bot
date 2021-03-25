import asyncio, aiohttp, aiofiles, asyncpool, logging, yarl, \
    datetime, decimal, discord, gspread, random, re, time, \
    traceback, scoreCalc, os, elo_rating, json5, osuapi, zipfile
from typing import *
from collections import defaultdict as dd

from osuapi import OsuApi, AHConnector

from bs4 import BeautifulSoup
from discord.ext import commands
from google.oauth2.service_account import Credentials

from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive

from help_texts import *

####################################################################################################################

scopes = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive',
]
jsonfile = 'friend-266503-91ab7f0dce62.json'
credentials = Credentials.from_service_account_file(jsonfile, scopes=scopes)
gs = gspread.authorize(credentials)
gs.login()
spreadsheet = "https://docs.google.com/spreadsheets/d/1SA2u-KgTsHcXcsGEbrcfqWugY7sgHIYJpPa5fxNEJYc/edit#gid=0"
doc = gs.open_by_url(spreadsheet)

worksheet = doc.worksheet('data')

gauth = GoogleAuth()
gauth.LoadCredentialsFile('credentials.json')
if gauth.credentials is None:
    gauth.LocalWebserverAuth()
elif gauth.access_token_expired:
    gauth.Refresh()
else:
    gauth.Authorize()
gauth.SaveCredentialsFile('credentials.json')
drive = GoogleDrive(gauth)

intents = discord.Intents.default()
intents.members = True
app = commands.Bot(command_prefix='m;', help_command=None, intents=intents)

ses: Optional[aiohttp.ClientSession] = None
api: Optional[OsuApi] = None

with open("key.txt", 'r') as f:
    token = f.read().strip()

with open("osu_login.json", 'r') as f:
    BASE_LOGIN_DATA = json5.load(f)

with open("osu_api_key.txt", 'r') as f:
    api_key = f.read().strip()

####################################################################################################################

url_base = "http://ops.dgsrz.com/profile.php?uid="
mapr = re.compile(r"(.*) [-] (.*) [(](.*)[)] [\[](.*)[]]")
playr = re.compile(r"(.*) / (.*) / (.*) / (.*)x / (.*)%")
missr = re.compile(r"[{]\"miss\":(\d+), \"hash\":.*[}]")

OSU_HOME = "https://osu.ppy.sh/home"
OSU_SESSION = "https://osu.ppy.sh/session"
OSU_BEATMAP_BASEURL = "https://osu.ppy.sh/beatmapsets/"

downloadpath = os.path.join('songs', '%s.zip')

prohibitted = re.compile(r"[\\/:*?\"<>|]")

d = decimal.Decimal

def getd(n: Union[int, float, str]):
    return d(str(n))

def halfup(n: d):
    return n.quantize(getd('1.'), rounding=decimal.ROUND_HALF_UP)

def neroscorev2(maxscore: d, score: d, acc: d, miss: d):
    s = 600000 * score / maxscore
    a = 400000 * (acc / 100) ** 4
    return halfup((s + a) * (1 - getd(0.003) * miss))

def jetonetv2(maxscore: d, score: d, acc: d, miss: d):
    s = 500000 * score / maxscore
    a = 500000 * (max(acc - 80, getd('0')) / 20) ** 2
    return halfup(s + a)

def osuv2(maxscore: d, score: d, acc: d, miss: d):
    s = 700000 * score / maxscore
    a = 300000 * (acc / 100) ** 10
    return halfup(s + a)

def v1(maxscore: d, score: d, acc: d, miss: d):
    return score

v2dict = {
    None    : v1,
    'nero2' : neroscorev2,
    'jet2'  : jetonetv2,
    'osu2'  : osuv2,
}

blank = '\u200b'

rkind = ['number', 'artist', 'author', 'title', 'diff']
rmeta = r'\$()*+.?[^{|'
rchange = re.compile(r'[\\/:*?\"<>|]')

analyze = re.compile(r"(?P<artist>.*) [-] (?P<title>.*) [(](?P<author>.*)[)] \[(?P<diff>.*)]")


####################################################################################################################


def makefull(**kwargs: str):
    return f"{kwargs['artist']} - {kwargs['title']} ({kwargs['author']}) [{kwargs['diff']}]"


def dice(s: str):
    s = s.partition('d')
    if s[1] == '':
        return None
    return tuple(str(random.randint(1, int(s[2]))) for _ in range(int(s[0])))


async def getrecent(_id: int) -> Optional[Tuple[Sequence[AnyStr], Sequence[AnyStr], Sequence[AnyStr]]]:
    url = url_base + str(_id)
    async with aiohttp.ClientSession() as s:
        html = await s.get(url)
    bs = BeautifulSoup(html.text, "html.parser")
    recent = bs.select_one("#activity > ul > li:nth-child(1)")
    recent_mapinfo = recent.select("a.clear > strong.block")[0].text
    recent_playinfo = recent.select("a.clear > small")[0].text
    recent_miss = recent.select("#statics")[0].text
    rmimatch = mapr.match(recent_mapinfo)
    if rmimatch is None:
        return None
    return (rmimatch.groups(),
            playr.match(recent_playinfo).groups(),
            missr.match(recent_miss).groups())


def is_owner():
    async def predicate(ctx):
        return ctx.author.id == 327835849142173696
    return commands.check(predicate)


####################################################################################################################

class Timer:
    def __init__(self, ch: discord.TextChannel, name: str, seconds: Union[float, d], async_callback=None, args=None):
        self.channel: discord.TextChannel = ch
        self.name: str = name
        self.seconds: float = seconds
        self.start_time: datetime.datetime = datetime.datetime.utcnow()
        self.loop = asyncio.get_event_loop()
        self.message: Optional[discord.Message] = None
        self.done = False
        self.callback = async_callback
        self.args = None

        self.task: asyncio.Task = loop.create_task(self.run())

    async def run(self):
        try:
            self.message = await self.channel.send(embed=discord.Embed(
                title="타이머 작동 시작!",
                description=f"타이머 이름 : {self.name}\n"
                            f"타이머 시간 : {self.seconds}",
                color=discord.Colour.dark_orange()
            ))
            await asyncio.sleep(self.seconds)
            await self.timeover()
        except asyncio.CancelledError:
            await self.cancel()
        finally:
            if self.callback:
                if self.args:
                    await self.callback(self.task.cancelled(), *self.args)
                else:
                    await self.callback(self.task.cancelled())

    async def timeover(self):
        await self.message.edit(embed=discord.Embed(
            title="타임 오버!",
            description=f"타이머 이름 : {self.name}\n"
                        f"타이머 시간 : {self.seconds}",
            color=discord.Colour.dark_grey()
        ))
        self.done = True

    async def cancel(self):
        if self.task.done() or self.task.cancelled():
            return
        self.task.cancel()
        await self.message.edit(embed=discord.Embed(
            title="타이머 강제 중지!",
            description=f"타이머 이름 : {self.name}\n"
                        f"타이머 시간 : {self.seconds}",
            color=discord.Colour.dark_red()
        ))
        self.done = True

    def left_sec(self) -> float:
        return self.seconds - ((datetime.datetime.utcnow() - self.start_time).total_seconds())


####################################################################################################################


def getusername(x: int) -> str:
    if member_names.get(x) is None:
        user = app.get_user(x)
        if user is None:
            user = app.fetch_user(x)
        member_names[x] = user.name
    return member_names[x]


visibleinfo = ['artist', 'title', 'author', 'diff']
modes = ['NM', 'HD', 'HR', 'DT', 'FM', 'TB']
modetoint = {
    'None': 0,
    'Hidden': 1,
    'HardRock': 2,
    'DoubleTime': 4,
    'NoFail': 8,
    'HalfTime': 16,
    'NightCore': 32,
    'Easy': 64
}
infotoint = {
    'artist': 1,
    'title': 2,
    'author': 4,
    'diff': 8,
    'mode': 16
}

timer_color = [0x800000, 0xff8000, 0x00ff00]

class Scrim:
    def __init__(self, ctx: discord.ext.commands.Context):
        self.loop = asyncio.get_event_loop()
        self.guild: discord.Guild = ctx.guild
        self.channel: discord.TextChannel = ctx.channel
        self.start_time = datetime.datetime.utcnow().strftime('%Y%m%d%H%M%S%f')

        self.match_task: Optional[asyncio.Task] = None

        self.team: Dict[str, Set[int]] = dict()
        # teamname : {member1_id, member2_id, ...}
        self.players: Set[int] = set()
        # {member1_id, member2_id, ...}
        self.findteam: Dict[int, str] = dict()
        # member_id : teamname
        self.setscore: Dict[str, int] = dict()
        # teamname : int
        self.score: Dict[int, Tuple[d, d, d]] = dict()
        # member_id : (score, acc, miss)

        self.map_artist: Optional[str] = None
        self.map_author: Optional[str] = None
        self.map_title: Optional[str] = None
        self.map_diff: Optional[str] = None
        self.map_time: Optional[int] = None

        self.map_number: Optional[str] = None
        self.map_mode: Optional[str] = None
        self.map_auto_score: Optional[int, dd] = None
        self.form: Optional[List[Union[re.Pattern, List[str]]]] = None

        self.availablemode: Dict[str, Iterable[int]] = {
            'NM': {0, 8},
            'HR': {2, 10},
            'HD': {1, 9},
            'DT': {4, 5, 12, 13},
            'FM': {0, 1, 2, 3, 8, 9, 10, 11},
            'TB': {0, 1, 2, 3, 8, 9, 10, 11},
        }

        self.setfuncs: Dict[str, Callable[[str], NoReturn]] = {
            'artist': self.setartist,
            'title' : self.settitle,
            'author': self.setauthor,
            'diff'  : self.setdiff,
            'number': self.setnumber,
            'mode'  : self.setmode,
            'autosc': self.setautoscore,
        }

        self.getfuncs: Dict[str, Callable[[], str]] = {
            'artist': self.getartist,
            'title' : self.gettitle,
            'author': self.getauthor,
            'diff'  : self.getdiff,
            'number': self.getnumber,
            'mode'  : self.getmode,
            'autosc': self.getautoscore,
        }

        self.log: List[str] = []

    async def maketeam(self, name: str):
        if self.team.get(name) is not None:
            await self.channel.send(embed=discord.Embed(
                title=f"\"{name}\" 팀은 이미 존재합니다!",
                description=f"현재 팀 리스트:\n{chr(10).join(self.team.keys())}",
                color=discord.Colour.dark_blue()
            ))
        else:
            self.team[name] = set()
            self.setscore[name] = 0
            await self.channel.send(embed=discord.Embed(
                title=f"\"{name}\" 팀을 추가했습니다!",
                description=f"현재 팀 리스트:\n{chr(10).join(self.team.keys())}",
                color=discord.Colour.blue()
            ))

    async def removeteam(self, name: str):
        if self.team.get(name) is None:
            await self.channel.send(embed=discord.Embed(
                title=f"\"{name}\"이란 팀은 존재하지 않습니다!",
                description=f"현재 팀 리스트:\n{chr(10).join(self.team.keys())}",
                color=discord.Colour.dark_blue()
            ))
        else:
            for p in self.team[name]:
                del self.findteam[p]
            del self.team[name], self.setscore[name]
            await self.channel.send(embed=discord.Embed(
                title=f"\"{name}\" 팀이 해산되었습니다!",
                description=f"현재 팀 리스트:\n{chr(10).join(self.team.keys())}",
                color=discord.Colour.blue()
            ))

    async def addplayer(self, name: str, member: Optional[discord.Member]):
        if not member:
            return
        mid = member.id
        temp = self.findteam.get(mid)
        if temp:
            await self.channel.send(embed=discord.Embed(
                title=f"플레이어 \"{member.name}\"님은 이미 \"{temp}\" 팀에 들어가 있습니다!",
                description=f"`m;out`으로 현재 팀에서 나온 다음에 명령어를 다시 입력해주세요."
            ))
        elif self.team.get(name) is None:
            await self.channel.send(embed=discord.Embed(
                title=f"\"{name}\"이란 팀은 존재하지 않습니다!",
                description=f"현재 팀 리스트:\n{chr(10).join(self.team.keys())}",
                color=discord.Colour.dark_blue()
            ))
        else:
            self.findteam[mid] = name
            self.team[name].add(mid)
            self.players.add(mid)
            self.score[mid] = (getd(0), getd(0), getd(0))
            await self.channel.send(embed=discord.Embed(
                title=f"플레이어 \"{member.name}\"님이 \"{name}\"팀에 참가합니다!",
                description=f"현재 \"{name}\"팀 플레이어 리스트:\n"
                            f"{chr(10).join(getusername(pl) for pl in self.team[name])}",
                color=discord.Colour.blue()
            ))

    async def removeplayer(self, member: Optional[discord.Member]):
        if not member:
            return
        mid = member.id
        temp = self.findteam.get(mid)
        if mid not in self.players:
            await self.channel.send(embed=discord.Embed(
                title=f"플레이어 \"{member.name}\"님은 어느 팀에도 속해있지 않습니다!",
                description=f"일단 참가하고나서 해주시죠."
            ))
        else:
            del self.findteam[mid], self.score[mid]
            self.team[temp].remove(mid)
            self.players.remove(mid)
            await self.channel.send(embed=discord.Embed(
                title=f"플레이어 \"{member.name}\"님이 \"{temp}\"팀을 떠납니다!",
                description=f"현재 \"{temp}\"팀 플레이어 리스트:\n"
                            f"{chr(10).join(getusername(pl) for pl in self.team[temp])}",
                color=discord.Colour.blue()
            ))

    async def addscore(self, member: Optional[discord.Member], score: int, acc: float, miss: int):
        if not member:
            return
        mid = member.id
        if mid not in self.players:
            await self.channel.send(embed=discord.Embed(
                title=f"플레이어 \"{member.name}\"님은 어느 팀에도 속해있지 않습니다!",
                description=f"일단 참가하고나서 해주시죠."
            ))
        else:
            self.score[mid] = (getd(score), getd(acc), getd(miss))
            await self.channel.send(embed=discord.Embed(
                title=f"플레이어 \"{member.name}\"님의 점수를 추가(또는 수정)했습니다!",
                description=f"\"{self.findteam[mid]}\"팀 <== {score}, {acc}%, {miss}xMISS",
                color=discord.Colour.blue()
            ))

    async def removescore(self, member: Optional[discord.Member]):
        if not member:
            return
        mid = member.id
        if mid not in self.players:
            await self.channel.send(embed=discord.Embed(
                title=f"플레이어 \"{member.name}\"님은 어느 팀에도 속해있지 않습니다!",
                description=f"일단 참가하고나서 해주시죠."
            ))
        else:
            self.score[mid] = (getd(0), getd(0), getd(0))
            await self.channel.send(embed=discord.Embed(
                title=f"플레이어 \"{member.name}\"님의 점수를 삭제했습니다!",
                color=discord.Colour.blue()
            ))

    async def submit(self, calcmode: Optional[str]):
        if v2dict.get(calcmode) is None:
            await self.channel.send(embed=discord.Embed(
                title="존재하지 않는 계산 방식입니다!",
                description="(입력없음), nero2, jet2, osu2 중 하나여야 합니다."
            ))
            return
        elif calcmode and (self.getautoscore() == -1):
            await self.channel.send(embed=discord.Embed(
                title="v2를 계산하기 위해서는 오토점수가 필요합니다!",
                description="`m;mapscore`로 오토점수를 등록해주세요!"
            ))
            return
        calcf = v2dict[calcmode]
        resultmessage = await self.channel.send(embed=discord.Embed(
            title="계산 중...",
            color=discord.Colour.orange()
        ))
        calculatedscores = dict()
        for p in self.score:
            calculatedscores[p] = calcf(self.map_auto_score, *self.score[p])
        teamscore = dict()
        for t in self.team:
            teamscore[t] = 0
            for p in self.team[t]:
                teamscore[t] += calculatedscores[p]
        winnerteam = list(filter(
            lambda x: teamscore[x] == max(teamscore.values()),
            teamscore.keys()
        ))
        for w in winnerteam:
            self.setscore[w] += 1
        desc = ', '.join('"'+t+'"' for t in winnerteam)
        sendtxt = discord.Embed(
            title="========= !매치 종료! =========",
            description=f"__**팀 {desc} 승리!**__",
            color=discord.Colour.red()
        )
        sendtxt.add_field(
            name="맵 정보",
            value=self.getmapfull(),
            inline=False
        )
        sendtxt.add_field(
            name=blank,
            value='='*20+'\n'+blank,
            inline=False
        )
        for t in teamscore:
            sendtxt.add_field(
                name=f"*\"{t}\"팀 결과 : {teamscore[t]}*",
                value='\n'.join(f"{getusername(p)} : "
                                f"{' / '.join(str(x) for x in self.score[p])} = "
                                f"{calculatedscores[p]}" for p in self.team[t])+'\n',
                inline=False
            )
        sendtxt.add_field(
            name=blank,
            value='='*20+'\n'+blank,
            inline=False
        )
        sendtxt.add_field(
            name="__현재 점수:__",
            value='\n'.join(f"**{t} : {self.setscore[t]}**" for t in teamscore),
            inline=False
        )
        await resultmessage.edit(embed=sendtxt)
        logtxt = [f'Map         : {self.getmapfull()}', f'MapNick     : {self.map_number}',
                  f'CalcFormula : {calcmode if calcmode else "V1"}', f'Winner Team : {desc}']
        for t in self.team:
            logtxt.append(f'\nTeam {t} = {teamscore[t]}')
            for p in self.team[t]:
                logtxt.append(f"Player {getusername(p)} = {calculatedscores[p]} "
                              f"({' / '.join(str(x) for x in self.score[p])})")
        self.log.append('\n'.join(logtxt))
        self.resetmap()

    def resetmap(self):
        self.map_artist = None
        self.map_author = None
        self.map_title = None
        self.map_diff = None
        self.map_number = None
        self.map_mode = None
        self.map_auto_score = None
        self.map_time = None
        for p in self.score:
            self.score[p] = (getd(0), getd(0), getd(0))

    def setartist(self, artist: str):
        self.map_artist = artist

    def getartist(self) -> str:
        return self.map_artist if self.map_artist else ''

    def settitle(self, title: str):
        self.map_title = title

    def gettitle(self) -> str:
        return self.map_title if self.map_title else ''

    def setauthor(self, author: str):
        self.map_author = author

    def getauthor(self) -> str:
        return self.map_author if self.map_author else ''

    def setdiff(self, diff: str):
        self.map_diff = diff

    def getdiff(self) -> str:
        return self.map_diff if self.map_diff else ''

    def setnumber(self, number: str):
        self.map_number = number

    def getnumber(self) -> str:
        return self.map_number if self.map_number else '-'

    def setmode(self, mode: str):
        self.map_mode = mode

    def getmode(self) -> str:
        return self.map_mode if self.map_mode else '-'

    def setautoscore(self, score: Union[int, d]):
        self.map_auto_score = score

    def getautoscore(self) -> Union[int, d]:
        return self.map_auto_score if self.map_auto_score else -1

    def setmaptime(self, t: Union[int, d]):
        self.map_time = t

    def getmaptime(self) -> Union[int, d]:
        return self.map_time if self.map_time else -1

    def setmapinfo(self, infostr: str):
        m = analyze.match(infostr)
        if m is None:
            return True
        for k in visibleinfo:
            if m.group(k) != '':
                self.setfuncs[k](m.group(k))

    def getmapinfo(self) -> Dict[str, str]:
        res = dict()
        for k in visibleinfo:
            res[k] = self.getfuncs[k]()
        return res

    def getmapfull(self):
        return makefull(**self.getmapinfo())

    async def setform(self, formstr: str):
        args = list()
        for k in rkind:
            findks = re.findall(k, formstr)
            if len(findks):
                args.append(k)
            elif len(findks) > 1:
                await self.channel.send(embed=discord.Embed(
                    title="각 단어는 하나씩만 들어가야 합니다!",
                    color=discord.Colour.dark_red()
                ))
                return
        for c in rmeta:
            formstr = formstr.replace(c, '\\' + c)
        for a in args:
            formstr = formstr.replace(a, f'(?P<{a}>.*?)')
        self.form = [re.compile(formstr), args]
        await self.channel.send(embed=discord.Embed(
            title="형식 지정 완료!",
            description=f"RegEx 패턴 : `{self.form[0].pattern}`",
            color=discord.Colour.blue()
        ))

    def setmoderule(
            self,
            nm: Optional[Iterable[int]],
            hd: Optional[Iterable[int]],
            hr: Optional[Iterable[int]],
            dt: Optional[Iterable[int]],
            fm: Optional[Iterable[int]],
            tb: Optional[Iterable[int]]
    ):
        if nm:
            self.availablemode['NM'] = nm
        if hd:
            self.availablemode['HD'] = hd
        if hr:
            self.availablemode['HR'] = hr
        if dt:
            self.availablemode['DT'] = dt
        if fm:
            self.availablemode['FM'] = fm
        if tb:
            self.availablemode['TB'] = tb

    async def onlineload(self, checkbit: Optional[int] = None):
        desc = '====== < 계산 로그 > ======'
        resultmessage: discord.Message = await self.channel.send(embed=discord.Embed(
            title="계산 중...",
            description=desc,
            color=discord.Colour.orange()
        ))
        for team in self.team:
            for player in self.team[team]:
                desc += '\n'
                await resultmessage.edit(embed=discord.Embed(
                    title="계산 중...",
                    description=desc,
                    color=discord.Colour.orange()
                ))
                if uids.get(player) is None:
                    desc += f"등록 실패 : " \
                            f"{getusername(player)}의 UID가 등록되어있지 않음"
                    continue
                player_recent_info = await getrecent(uids[player])
                if player_recent_info is None:
                    desc += f"등록 실패 : " \
                            f"{getusername(player)}의 최근 플레이 정보가 기본 형식에 맞지 않음"
                p = dict()
                p['artist'], p['title'], p['author'], p['diff'] = player_recent_info[0]
                p['score'] = int(player_recent_info[1][1].replace(',', ''))
                p['acc'] = float(player_recent_info[1][4])
                p['miss'] = int(float(player_recent_info[2][0]))
                p['modes'] = set(player_recent_info[1][2].split(', '))
                flag = False
                if self.form is not None:
                    checkbit = 0
                    m = self.form[0].match(p['diff'])
                    if m is None:
                        desc += f"등록 실패 : " \
                                f"{getusername(player)}의 최근 플레이 난이도명이 저장된 형식에 맞지 않음 " \
                                f"(플레이어 난이도명 : {p['diff']})"
                        continue
                    for k in self.form[1]:
                        if k == 'number':
                            mnum = self.map_number.split(';')[-1]
                            pnum = m.group(k)
                            if mnum != pnum:
                                flag = True
                                desc += f"등록 실패 : " \
                                        f"{getusername(player)}의 맵 번호가 다름 (플레이어 맵 번호 : {pnum})"
                                break
                            continue
                        p[k] = m.group(k)
                        checkbit |= infotoint[k]
                if checkbit is None:
                    checkbit = 31
                for k in ['artist', 'title', 'author', 'diff']:
                    if flag:
                        break
                    if checkbit & infotoint[k]:
                        nowk = self.getfuncs[k]()
                        nowk_edited = rchange.sub('', nowk).replace('\'', ' ')
                        if nowk != p[k]:
                            flag = True
                            desc += f"등록 실패 : " \
                                    f"{getusername(player)}의 {k}가 다름 " \
                                    f"(현재 {k} : {nowk_edited} {'('+nowk+') ' if nowk!=nowk_edited else ''}/ " \
                                    f"플레이어 {k} : {p[k]})"
                if flag:
                    continue
                if self.map_mode is not None:
                    pmodeint = 0
                    for md in p['modes']:
                        if modetoint.get(md):
                            pmodeint |= modetoint[md]
                    if pmodeint not in self.availablemode[self.map_mode]:
                        desc += f"등록 실패 : " \
                                f"{getusername(player)}의 모드가 조건에 맞지 않음 " \
                                f"(현재 가능한 모드 숫자 : {self.availablemode[self.map_mode]} / " \
                                f"플레이어 모드 숫자 : {pmodeint})"
                        continue
                self.score[player] = (getd(p['score']), getd(p['acc']), getd(p['miss']))
                desc += f"등록 완료! : " \
                        f"{getusername(player)}의 점수 " \
                        f"{self.score[player][0]}, {self.score[player][1]}%, {self.score[player][2]}xMISS"
        await resultmessage.edit(embed=discord.Embed(
            title="계산 완료!",
            description=desc,
            color=discord.Colour.green()
        ))

    async def end(self):
        winnerteam = list(filter(
            lambda x: self.setscore[x] == max(self.setscore.values()),
            self.setscore.keys()
        ))
        sendtxt = discord.Embed(
            title="========= !스크림 종료! =========",
            description="팀 " + ', '.join(f"\"{w}\"" for w in winnerteam) + " 최종 우승!",
            color=discord.Colour.magenta()
        )
        sendtxt.add_field(
            name=blank,
            value='='*20+'\n'+blank,
            inline=False
        )
        sendtxt.add_field(
            name="최종 결과:",
            value='\n'.join(f"{t} : {self.setscore[t]}" for t in self.setscore)
        )
        sendtxt.add_field(
            name=blank,
            value='='*20+'\n'+blank,
            inline=False
        )
        sendtxt.add_field(
            name="수고하셨습니다!",
            value='스크림 정보가 자동으로 초기화됩니다.\n'
                  '스크림 기록은 아래 파일을 다운받아 텍스트 에디터로 열어보실 수 있습니다.',
            inline=False
        )
        filename = f'scrim{self.start_time}.log'
        with open(filename, 'w') as _f:
            _f.write('\n\n====================\n\n'.join(self.log))
        with open(filename, 'rb') as _f:
            await self.channel.send(embed=sendtxt, file=discord.File(_f, filename))
        os.remove(filename)

    async def do_match_start(self):
        if self.match_task is None or self.match_task.done():
            self.match_task = asyncio.create_task(self.match_start())
        else:
            await self.channel.send(embed=discord.Embed(
                title="매치가 이미 진행 중입니다!",
                description="매치가 끝난 후 다시 시도해주세요.",
                color=discord.Colour.dark_red()
            ))

    async def match_start(self):
        if self.map_time is None:
            await self.channel.send(embed=discord.Embed(
                title="맵 타임이 설정되지 않았습니다!",
                description="`m;maptime`으로 맵 타임을 설정해주세요.",
                color=discord.Colour.dark_red()
            ))
            return
        try:
            await self.channel.send(embed=discord.Embed(
                title="매치 시작!",
                description=f"맵 정보 : {self.getmapfull()}\n"
                            f"맵 번호 : {self.getnumber()} / 모드 : {self.getmode()}\n"
                            f"맵 SS 점수 : {self.getautoscore()} / 맵 시간(초) : {self.getmaptime()}",
                color=discord.Colour.from_rgb(255, 255, 0)
            ))
            a = self.map_time
            timermessage = await self.channel.send(embed=discord.Embed(
                title=f"매치 타이머 준비중",
                color=discord.Colour.from_rgb(0, 0, 255)
            ))
            for i in range(self.map_time):
                a -= 1
                await timermessage.edit(embed=discord.Embed(
                    title=f"{a//60}분 {a%60}초 남았습니다...",
                    color=discord.Colour(timer_color[int(a*3/self.map_time)])
                ))
                await asyncio.sleep(1)
            timermessage = await self.channel.send(embed=discord.Embed(
                title=f"매치 시간 종료!",
                color=discord.Colour.from_rgb(128, 128, 255)
            ))
            for i in range(30, -1, -1):
                await timermessage.edit(embed=discord.Embed(
                    title=f"매치 시간 종료!",
                    description=f"추가 시간 {i}초 남았습니다...",
                    color=discord.Colour.from_rgb(128, 128, 255)
                ))
                await asyncio.sleep(1)
            await self.channel.send(embed=discord.Embed(
                title=f"매치 추가 시간 종료!",
                description="온라인 기록을 불러옵니다...",
                color=discord.Colour.from_rgb(128, 128, 255)
            ))
            await self.onlineload()
            await self.submit('nero2')
        except asyncio.CancelledError:
            await self.channel.send(embed=discord.Embed(
                title="매치가 중단되었습니다!",
                color=discord.Colour.dark_red()
            ))
            return


member_names: Dict[int, str] = dict()
datas: dd[Dict[int, dd[Dict[int, Dict[str, Union[int, Scrim]]], Callable[[], Dict]]]] = \
    dd(lambda: dd(lambda: {'valid': False, 'scrim': None}))
uids: dd[int, int] = dd(int)
ratings: dd[int, d] = dd(d)
timers: dd[str, Optional[Timer]] = dd(lambda: None)
timer_count = 0

with open('uids.txt', 'r') as f:
    while data := f.readline():
        discordid, userid = data.split(' ')
        uids[int(discordid)] = int(userid)

with open('ratings.txt', 'r') as f:
    while data := f.readline():
        userid, r = data.split(' ')
        ratings[int(userid)] = getd(r)

####################################################################################################################

class Match:
    def __init__(self, ctx: discord.ext.commands.Context,
                 player: discord.Member, opponent: discord.Member, bo: int = 7):
        self.channel = ctx.channel
        self.player = player
        self.opponent = opponent

        self.mappoolmaker: Optional[MappoolMaker] = None
        self.map_order: List[str] = []

        self.scrim = Scrim(ctx)
        self.made_time = datetime.datetime.utcnow().strftime("%y%m%d%H%M%S%f")
        self.timer: Optional[Timer] = None

        self.round = -1
        # -2 = 매치 생성 전
        # -1 = 플레이어 참가 대기
        # 0 = 맵풀 다운로드 대기
        # n = n라운드 준비 대기
        self.totalrounds = 2 * bo - 1
        self.abort = False

        self.player_ready: bool = False
        self.opponent_ready: bool = False

    async def trigger_ready(self, subj):
        if self.player == subj:
            self.player_ready = True
        elif self.opponent == subj:
            self.opponent_ready = True
        else:
            return
        await self.channel.send(embed=discord.Embed(
            title=f"{subj} 준비됨!",
            color=discord.Colour.green()
        ))

    async def trigger_unready(self, subj):
        if self.player == subj:
            self.player_ready = False
        elif self.opponent == subj:
            self.opponent_ready = False
        else:
            return
        await self.channel.send(embed=discord.Embed(
            title=f"{subj} 준비 해제됨!",
            color=discord.Colour.red()
        ))

    def is_all_ready(self):
        return self.player_ready and self.opponent_ready

    def reset_ready(self):
        self.player_ready = False
        self.opponent_ready = False

    async def go_next_status(self, timer_cancelled):
        if self.round == -1 and self.is_all_ready():
            if timer_cancelled:
                self.round = 0
                await self.channel.send(embed=discord.Embed(
                    title="모두 참가가 완료되었습니다!",
                    description="스크림 & 맵풀 생성 중입니다...",
                    color=discord.Colour.dark_red()
                ))
                await self.scrim.maketeam(self.player.display_name)
                await self.scrim.maketeam(self.opponent.display_name)
                await self.scrim.addplayer(self.player.display_name, self.player)
                await self.scrim.addplayer(self.opponent.display_name, self.opponent)
            else:
                await self.channel.send(embed=discord.Embed(
                    title="상대가 참가하지 않았습니다.",
                    description="매치가 취소되고, 두 유저는 다시 매칭 풀에 들어갑니다.",
                    color=discord.Colour.dark_red()
                ))
                self.abort = True
        elif self.round == 0 and self.is_all_ready():
            if timer_cancelled:
                self.round = 1
                await self.channel.send(embed=discord.Embed(
                    title="모두 준비되었습니다!",
                    description="매치 시작 준비 중입니다...",
                    color=discord.Colour.dark_red()
                ))
                await self.scrim.setform('[number] artist - title [diff]')
            else:
                await self.channel.send(embed=discord.Embed(
                    title="상대가 준비되지 않았습니다.",
                    description="인터넷 문제를 가지고 있을 수 있습니다.\n"
                                "매치 진행에 어려움이 있을 수 있기 때문에 매치를 취소합니다.",
                    color=discord.Colour.dark_red()
                ))
                self.abort = True
        else:
            self.round += 1
            if self.is_all_ready() and timer_cancelled:
                message = await self.channel.send(embed=discord.Embed(
                    title="모두 준비되었습니다!",
                    description=f"10초 뒤 {self.round}라운드가 시작됩니다...",
                    color=discord.Colour.purple()
                ))
                for i in range(9, -1, -1):
                    await message.edit(embed=discord.Embed(
                        title="모두 준비되었습니다!",
                        description=f"**{i}**초 뒤 {self.round}라운드가 시작됩니다...",
                        color=discord.Colour.purple()
                    ))
                    await asyncio.sleep(1)
            else:
                message = await self.channel.send(embed=discord.Embed(
                    title="준비 시간이 끝났습니다!",
                    description=f"10초 뒤 {self.round}라운드를 **강제로 시작**합니다...",
                    color=discord.Colour.purple()
                ))
                for i in range(9, -1, -1):
                    await message.edit(embed=discord.Embed(
                        title="준비 시간이 끝났습니다!",
                        description=f"**{i}**초 뒤 {self.round}라운드를 **강제로 시작**합니다...",
                        color=discord.Colour.purple()
                    ))
                    await asyncio.sleep(1)
            await self.scrim.do_match_start()

    async def do_progress(self):
        if self.abort:
            return
        elif self.round == -1:
            await self.channel.send(
                f"{self.player.mention} {self.opponent.mention}",
                embed=discord.Embed(
                    title="매치가 생성되었습니다!",
                    description="이 메세지가 올라온 후 2분 안에 `rdy`를 말해주세요!"
                )
            )
            self.timer = Timer(self.channel, f"Match_{self.made_time}", 120, self.go_next_status)
        elif self.round == 0:
            statusmessage = await self.channel.send(embed=discord.Embed(
                title="맵풀 다운로드 상태 메세지입니다.",
                description="이 문구가 5초 이상 바뀌지 않는다면 개발자를 불러주세요.",
                color=discord.Colour.orange()
            ))
            self.mappoolmaker = MappoolMaker(statusmessage)

            # 레이팅에 맞춰서 맵 번호 등록

            self.map_order.extend(self.mappoolmaker.maps.keys())
            random.shuffle(self.map_order)
            mappool_link = await self.mappoolmaker.execute_osz()

            if mappool_link is False:
                print("FATAL ERROR : SESSION CLOSED")
                return
            await self.channel.send(embed=discord.Embed(
                title="맵풀이 완성되었습니다!",
                description=f"다음 링크에서 맵풀을 다운로드해주세요 : {mappool_link}\n"
                            f"맵풀 다운로드 로그 중 다운로드에 실패한 맵풀이 있다면 "
                            f"이 매치를 취소시키고 개발자를 불러주세요\n"
                            f"다운로드가 완료되었고, 준비가 되었다면 `rdy`를 말해주세요!\n"
                            f"다운로드 제한 시간은 5분입니다.",
                color=discord.Colour.blue()
            ))
            self.timer = Timer(self.channel, f"Match_{self.made_time}", 300, self.go_next_status)
        elif self.round > self.totalrounds:
            await self.scrim.end()
            self.abort = True
        else:
            now_mapnum = self.map_order[self.round - 1]
            now_beatmap: osuapi.osu.Beatmap = self.mappoolmaker.beatmap_objects[now_mapnum]
            self.scrim.setnumber(now_mapnum)
            self.scrim.setartist(now_beatmap.artist)
            self.scrim.setauthor(now_beatmap.creator)
            self.scrim.settitle(now_beatmap.title)
            self.scrim.setdiff(now_beatmap.version)
            self.scrim.setmaptime(now_beatmap.total_length)
            self.scrim.setmode(now_mapnum[:2])
            scorecalc = scoreCalc.scoreCalc(os.path.join(
                self.mappoolmaker.save_folder_path, f"{now_beatmap.beatmapset_id}+{now_beatmap.beatmap_id}.osz"))
            self.scrim.setautoscore(scorecalc.getAutoScore())
            await self.channel.send(embed=discord.Embed(
                title=f"{self.round}라운드 준비!",
                description="2분 안에 `rdy`를 말해주세요!",
                color=discord.Colour.orange()
            ))
            self.timer = Timer(self.channel, f"Match_{self.made_time}", 120, self.go_next_status)


####################################################################################################################

class MappoolMaker:
    def __init__(self, message, session=ses):
        self.maps: Dict[str, Tuple[int, int]] = dict()  # MODE: (MAPSET ID, MAPDIFF ID)
        self.beatmap_objects: Dict[str, osuapi.osu.Beatmap] = dict()
        self.queue = asyncio.Queue()
        self.session: Optional[aiohttp.ClientSession] = session
        self.message: Optional[discord.Message] = message

        self.pool_name = f'Match_{datetime.datetime.utcnow().strftime("%y%m%d%H%M%S%f")}'
        self.save_folder_path = os.path.join('songs', self.pool_name)

    def add_map(self, mode: str, mapid: int, diffid: int):
        self.maps[mode] = (mapid, diffid)

    def remove_map(self, mode: str):
        del self.maps[mode]

    async def downloadBeatmap(self, number: int):
        downloadurl = OSU_BEATMAP_BASEURL + str(number)
        async with self.session.get(downloadurl + '/download', headers={"referer": downloadurl}) as res:
            if res.status < 400:
                async with aiofiles.open(downloadpath % number, 'wb') as f_:
                    await f_.write(await res.read())
                print(f'{number}번 비트맵셋 다운로드 완료')
            else:
                print(f'{number}번 비트맵셋 다운로드 실패 ({res.status})')
                await self.queue.put((number, False))
                return
        await self.queue.put((number, True))

    async def show_result(self):
        desc = blank
        await self.message.edit(embed=discord.Embed(
            title="맵풀 다운로드 중",
            description=desc,
            color=discord.Colour.orange()
        ))
        while True:
            v = await self.queue.get()
            if v is None:
                await self.message.edit(embed=discord.Embed(
                    title="맵풀 다운로드 완료",
                    description=desc,
                    color=discord.Colour.orange()
                ))
                break
            if v[1]:
                desc += f"{v[0]}번 다운로드 성공"
            else:
                desc += f"{v[0]}번 다운로드 실패"
            await self.message.edit(embed=discord.Embed(
                title="맵풀 다운로드 중",
                description=desc,
                color=discord.Colour.orange()
            ))

    async def execute_osz(self) -> Union[str, bool]:
        if self.session.closed:
            return False
        t = asyncio.create_task(self.show_result())
        async with asyncpool.AsyncPool(loop, num_workers=4, name="DownloaderPool",
                                       logger=logging.getLogger("DownloaderPool"),
                                       worker_co=self.downloadBeatmap, max_task_time=300,
                                       log_every_n=10) as pool:
            for x in self.maps:
                mapid = self.maps[x][0]
                await pool.push(mapid)

        await self.queue.put(None)
        await t

        try:
            os.mkdir(self.save_folder_path)
        except FileExistsError:
            pass

        for x in self.maps:
            beatmap_info: osuapi.osu.Beatmap = (await api.get_beatmaps(beatmap_id=self.maps[x][1]))[0]
            self.beatmap_objects[x] = beatmap_info

            zf = zipfile.ZipFile(downloadpath % beatmap_info.beatmapset_id)
            target_name = f"{beatmap_info.artist} - {beatmap_info.title} " \
                          f"({beatmap_info.creator}) [{beatmap_info.version}].osu"
            try:
                target_name_search = prohibitted.sub('', target_name.lower())
                zipfile_list = zf.namelist()
                extracted_path = None
                osufile_name = None
                for zfn in zipfile_list:
                    if zfn.lower() == target_name_search:
                        osufile_name = zfn
                        extracted_path = zf.extract(zfn, self.save_folder_path)
                        break
                assert extracted_path is not None
            except AssertionError:
                print(f"파일이 없음 : {target_name}")
                continue

            texts = ''
            async with aiofiles.open(extracted_path, 'r', encoding='utf-8') as osufile:
                texts = await osufile.readlines()
                for i in range(len(texts)):
                    text = texts[i].rstrip()
                    if m := re.match(r'AudioFilename:\s?(.*)', text):
                        audio_path = m.group(1)
                        audio_extracted = zf.extract(audio_path, self.save_folder_path)
                        after_filename = f"{x}.mp3"
                        os.rename(audio_extracted, audio_extracted.replace(audio_path, after_filename))
                        texts[i] = texts[i].replace(audio_path, after_filename)
                    elif m := re.match(r'\d+,\d+,\"(.*?)\".*', text):
                        background_path = m.group(1)
                        extension = background_path.split('.')[-1]
                        bg_extracted = zf.extract(background_path, self.save_folder_path)
                        after_filename = f"{x}.{extension}"
                        os.rename(bg_extracted, bg_extracted.replace(background_path, after_filename))
                        texts[i] = texts[i].replace(background_path, after_filename)
                    elif m := re.match(r'Title(Unicode)?[:](.*)', text):
                        orig_title = m.group(2)
                        texts[i] = texts[i].replace(orig_title, f'Mappool for {self.pool_name}')
                    elif m := re.match(r'Artist(Unicode)?[:](.*)', text):
                        orig_artist = m.group(2)
                        texts[i] = texts[i].replace(orig_artist, f'V.A.')
                    elif m := re.match(r'Version[:](.*)', text):
                        orig_diffname = m.group(1)
                        texts[i] = texts[i].replace(
                            orig_diffname,
                            f"[{x}] {beatmap_info.artist} - {beatmap_info.title} [{beatmap_info.version}]"
                        )

            async with aiofiles.open(extracted_path, 'w', encoding='utf-8') as osufile:
                await osufile.writelines(texts)

            os.rename(extracted_path, extracted_path.replace(osufile_name, f"{x}.osu"))
            os.remove(extracted_path)

        result_zipfile = f"{self.pool_name}.zip"
        with zipfile.ZipFile(result_zipfile, 'w') as zf:
            for fn in os.listdir(self.save_folder_path):
                zf.write(os.path.join(self.save_folder_path, fn))

        # 이후 할 것
        # 1. 드라이브에 업로드
        # 2. 링크 전송

####################################################################################################################


helptxt = discord.Embed(title=helptxt_title, description=helptxt_desc, color=discord.Colour(0xfefefe))
helptxt.add_field(name=helptxt_forscrim_name, value=helptxt_forscrim_desc1, inline=False)
helptxt.add_field(name=blank, value=helptxt_forscrim_desc2, inline=False)
helptxt.add_field(name=blank, value=helptxt_forscrim_desc3, inline=False)
helptxt.add_field(name=blank, value=helptxt_forscrim_desc4, inline=False)
helptxt.add_field(name=helptxt_other_name, value=helptxt_other_desc, inline=False)


@app.event
async def on_ready():
    print(f"[{time.strftime('%Y-%m-%d %a %X', time.localtime(time.time()))}]")
    print("BOT NAME :", app.user.name)
    print("BOT ID   :", app.user.id)
    game = discord.Game("m;help")
    await app.change_presence(status=discord.Status.online, activity=game)
    print("==========BOT START==========")


@app.event
async def on_message(message):
    ch = message.channel
    p = message.author
    if p == app.user:
        return
    if isinstance(message.channel, discord.channel.DMChannel):
        print(
            f"[{time.strftime('%Y-%m-%d %a %X', time.localtime(time.time()))}] "
            f"[DM] <{p.name};{p.id}> {message.content}"
        )
    else:
        print(
            f"[{time.strftime('%Y-%m-%d %a %X', time.localtime(time.time()))}] "
            f"[{message.guild.name};{ch.name}] <{p.name};{p.id}> {message.content}"
        )
    if credentials.access_token_expired:
        gs.login()
    await app.process_commands(message)


@app.event
async def on_command_error(ctx, error):
    errortxt = ''.join(traceback.format_exception(type(error), error, error.__traceback__)).strip()
    print('================ ERROR ================')
    print(errortxt)
    print('=======================================')
    await ctx.send(f'에러 발생 :\n```{errortxt}```')


@app.command(name="help")
async def _help(ctx):
    await ctx.send(embed=helptxt)


@app.command()
async def ping(ctx):
    msgtime = ctx.message.created_at
    nowtime = datetime.datetime.utcnow()
    print(msgtime)
    print(nowtime)
    await ctx.send(f"Pong! `{(nowtime - msgtime).total_seconds() * 1000 :.4f}ms`")


@app.command()
async def roll(ctx, *dices: str):
    sendtxt = []
    for _d in dices:
        x = dice(_d)
        if not x:
            continue
        sendtxt.append(f"{_d}: **{' / '.join(x)}**")
    await ctx.send(embed=discord.Embed(title="주사위 결과", description='\n'.join(sendtxt)))


@app.command()
async def sheetslink(ctx):
    await ctx.send("https://docs.google.com/spreadsheets/d/1SA2u-KgTsHcXcsGEbrcfqWugY7sgHIYJpPa5fxNEJYc/edit#gid=0")


####################################################################################################################


@app.command()
@is_owner()
async def say(ctx, *, txt: str):
    if txt:
        await ctx.send(txt)


@app.command()
@is_owner()
async def sayresult(ctx, *, com: str):
    res = eval(com)
    await ctx.send('결과값 : `' + str(res) + '`')


@app.command()
@is_owner()
async def run(ctx, *, com: str):
    exec(com)
    await ctx.send('실행됨')


####################################################################################################################


@app.command()
async def make(ctx):
    s = datas[ctx.guild.id][ctx.channel.id]
    if s['valid']:
        await ctx.send("이미 스크림이 존재합니다.")
        return
    s['valid'] = 1
    s['scrim'] = Scrim(ctx)
    await ctx.send(embed=discord.Embed(
        title="스크림이 만들어졌습니다! | A scrim is made",
        description=f"서버/Guild : {ctx.guild}\n채널/Channel : {ctx.channel}",
        color=discord.Colour.green()
    ))


@app.command(aliases=['t'])
async def teamadd(ctx, *, name):
    s = datas[ctx.guild.id][ctx.channel.id]
    if s['valid']:
        await s['scrim'].maketeam(name)


@app.command(aliases=['tr'])
async def teamremove(ctx, *, name):
    s = datas[ctx.guild.id][ctx.channel.id]
    if s['valid']:
        await s['scrim'].removeteam(name)


@app.command(name="in")
async def _in(ctx, *, name):
    s = datas[ctx.guild.id][ctx.channel.id]
    if s['valid']:
        await s['scrim'].addplayer(name, ctx.author)


@app.command()
async def out(ctx):
    s = datas[ctx.guild.id][ctx.channel.id]
    if s['valid']:
        await s['scrim'].removeplayer(ctx.author)


@app.command(aliases=['score', 'sc'])
async def _score(ctx, sc: int, a: float = 0.0, m: int = 0):
    s = datas[ctx.guild.id][ctx.channel.id]
    if s['valid']:
        await s['scrim'].addscore(ctx.author, sc, a, m)


@app.command(aliases=['scr'])
async def scoreremove(ctx):
    s = datas[ctx.guild.id][ctx.channel.id]
    if s['valid']:
        await s['scrim'].removescore(ctx.author)


@app.command()
async def submit(ctx, calcmode: Optional[str] = None):
    s = datas[ctx.guild.id][ctx.channel.id]
    if s['valid']:
        await s['scrim'].submit(calcmode)

@app.command()
async def start(ctx):
    s = datas[ctx.guild.id][ctx.channel.id]
    if s['valid']:
        await s['scrim'].do_match_start()

@app.command()
async def abort(ctx):
    s = datas[ctx.guild.id][ctx.channel.id]
    if s['valid']:
        if not s['scrim'].match_task.done():
            s['scrim'].match_task.cancel()

@app.command()
async def end(ctx):
    s = datas[ctx.guild.id][ctx.channel.id]
    if s['valid']:
        await s['scrim'].end()
        del datas[ctx.guild.id][ctx.channel.id]

@app.command()
async def bind(ctx, number: int):
    mid = ctx.author.id
    uids[mid] = number
    await ctx.send(embed=discord.Embed(
        title=f'플레이어 \"{ctx.author.name}\"님을 UID {number}로 연결했습니다!',
        color=discord.Colour(0xfefefe)
    ))


@app.command(name="map")
async def _map(ctx, *, name: str):
    s = datas[ctx.guild.id][ctx.channel.id]
    if s['valid']:
        resultmessage = await ctx.send(embed=discord.Embed(
            title="계산 중...",
            color=discord.Colour.orange()
        ))
        scrim = s['scrim']
        t = scrim.setmapinfo(name)
        if t:
            try:
                target = worksheet.find(name)
            except gspread.exceptions.CellNotFound:
                await resultmessage.edit(embed=discord.Embed(
                    title=f"{name}을 찾지 못했습니다!",
                    description="오타가 있거나, 아직 봇 시트에 등록이 안 되어 있을 수 있습니다.",
                    color=discord.Colour.dark_red()
                ))
                return
            except Exception as e:
                await resultmessage.eddit(embed=discord.Embed(
                    title="오류 발생!",
                    description=f"오류 : `[{type(e)}] {e}`",
                    color=discord.Colour.dark_red()
                ))
                return
            values = worksheet.row_values(target.row)
            scrim.setfuncs['author'](values[0])
            scrim.setfuncs['artist'](values[1])
            scrim.setfuncs['title'](values[2])
            scrim.setfuncs['diff'](values[3])
            mapautosc = values[4]
            maptime_ = values[8]
            if mapautosc:
                scrim.setautoscore(int(mapautosc))
            if maptime_:
                scrim.setmaptime(int(maptime_))
            scrim.setnumber(name)
            scrim.setmode(re.findall('|'.join(modes), name.split(';')[-1])[0])
        await resultmessage.edit(embed=discord.Embed(
            title=f"설정 완료!",
            description=f"맵 정보 : {scrim.getmapfull()}\n"
                        f"맵 번호 : {scrim.getnumber()} / 모드 : {scrim.getmode()}\n"
                        f"맵 SS 점수 : {scrim.getautoscore()} / 맵 시간(초) : {scrim.getmaptime()}",
            color=discord.Colour.blue()
        ))


@app.command(aliases=['mm'])
async def mapmode(ctx, mode: str):
    s = datas[ctx.guild.id][ctx.channel.id]
    if s['valid']:
        resultmessage = await ctx.send(embed=discord.Embed(
            title="계산 중...",
            color=discord.Colour.orange()
        ))
        scrim = s['scrim']
        scrim.setmode(mode)
        await resultmessage.edit(embed=discord.Embed(
            title=f"설정 완료!",
            description=f"맵 정보 : {scrim.getmapfull()}\n"
                        f"맵 번호 : {scrim.getnumber()} / 모드 : {scrim.getmode()}\n"
                        f"맵 SS 점수 : {scrim.getautoscore()} / 맵 시간(초) : {scrim.getmaptime()}",
            color=discord.Colour.blue()
        ))

@app.command(aliases=['mt'])
async def maptime(ctx, _time: int):
    s = datas[ctx.guild.id][ctx.channel.id]
    if s['valid']:
        resultmessage = await ctx.send(embed=discord.Embed(
            title="계산 중...",
            color=discord.Colour.orange()
        ))
        scrim = s['scrim']
        scrim.setmaptime(_time)
        await resultmessage.edit(embed=discord.Embed(
            title=f"설정 완료!",
            description=f"맵 정보 : {scrim.getmapfull()}\n"
                        f"맵 번호 : {scrim.getnumber()} / 모드 : {scrim.getmode()}\n"
                        f"맵 SS 점수 : {scrim.getautoscore()} / 맵 시간(초) : {scrim.getmaptime()}",
            color=discord.Colour.blue()
        ))

@app.command(aliases=['ms'])
async def mapscore(ctx, sc_or_auto: Union[int, str], *, path: Optional[str] = None):
    s = datas[ctx.guild.id][ctx.channel.id]
    if s['valid']:
        resultmessage = await ctx.send(embed=discord.Embed(
            title="계산 중...",
            color=discord.Colour.orange()
        ))
        scrim = s['scrim']
        if sc_or_auto == 'auto':
            s = scoreCalc.scoreCalc(path)
            scrim.setautoscore(s.getAutoScore()[1])
            s.close()
        else:
            scrim.setautoscore(sc_or_auto)
        await resultmessage.edit(embed=discord.Embed(
            title=f"설정 완료!",
            description=f"맵 정보 : {scrim.getmapfull()}\n"
                        f"맵 번호 : {scrim.getnumber()} / 모드 : {scrim.getmode()}\n"
                        f"맵 SS 점수 : {scrim.getautoscore()} / 맵 시간(초) : {scrim.getmaptime()}",
            color=discord.Colour.blue()
        ))


@app.command(aliases=['l'])
async def onlineload(ctx, checkbit: Optional[int] = None):
    s = datas[ctx.guild.id][ctx.channel.id]
    if s['valid']:
        await s['scrim'].onlineload(checkbit)


@app.command()
async def form(ctx, *, f_: str):
    s = datas[ctx.guild.id][ctx.channel.id]
    if s['valid']:
        await s['scrim'].setform(f_)


@app.command(aliases=['mr'])
async def mapmoderule(
        ctx, 
        nm: Optional[str], 
        hd: Optional[str], 
        hr: Optional[str], 
        dt: Optional[str], 
        fm: Optional[str], 
        tb: Optional[str]
):
    s = datas[ctx.guild.id][ctx.channel.id]
    if s['valid']:
        def temp(x: Optional[str]):
            return set(map(int, x.split(',')))
        s['scrim'].setmoderule(temp(nm), temp(hd), temp(hr), temp(dt), temp(fm), temp(tb))

@app.command()
async def timer(ctx, action: Union[float, str], name: Optional[str] = None):
    if action == 'now':
        if timers.get(name) is None:
            await ctx.send(embed=discord.Embed(
                title=f"\"{name}\"이란 이름을 가진 타이머는 없습니다!",
                color=discord.Colour.dark_red()
            ))
        else:
            await ctx.send(embed=discord.Embed(
                title=f"\"{name}\" 타이머 남은 시간 :",
                description=f"{timers[name].left_sec()}초 남았습니다!"
            ))
    elif action == 'cancel':
        if timers.get(name) is None:
            await ctx.send(embed=discord.Embed(
                title=f"\"{name}\"이란 이름을 가진 타이머는 없습니다!",
                color=discord.Colour.dark_red()
            ))
        else:
            await timers[name].cancel()
    else:
        if name is None:
            global timer_count
            name = str(timer_count)
            timer_count += 1
        if not timers[name].done:
            await ctx.send(embed=discord.Embed(
                title=f"\"{name}\"이란 이름을 가진 타이머는 이미 작동하고 있습니다!",
                color=discord.Colour.dark_red()
            ))
            return
        timers[name] = Timer(ctx.channel, name, action)
        await ctx.send(embed=discord.Embed(
            title=f"\"{name}\" 타이머 설정 완료!",
            description=f"{timers[name].seconds}초로 설정되었습니다.",
            color=discord.Colour.blue()
        ))

@app.command()
async def calc(ctx, kind: str, maxscore: d, score: d, acc: d, miss: d):
    if kind == "nero2":
        result = neroscorev2(maxscore, score, acc, miss)
    elif kind == "jet2":
        result = jetonetv2(maxscore, score, acc, miss)
    elif kind == "osu2":
        result = osuv2(maxscore, score, acc, miss)
    else:
        await ctx.send(embed=discord.Embed(
            title=f"\"{kind}\"라는 계산 방식이 없습니다!",
            description="nero2, jet2, osu2 중 하나를 입력해주세요.",
            color=discord.Colour.dark_red()
        ))
        return
    await ctx.send(embed=discord.Embed(
        title=f"계산 결과 ({kind})",
        description=f"maxscore = {maxscore}\n"
                    f"score = {score}\n"
                    f"acc = {acc}\n"
                    f"miss = {miss}\n\n"
                    f"calculated = **{result}**",
        color=discord.Colour.dark_blue()
    ))

@app.command()
async def now(ctx):
    s = datas[ctx.guild.id][ctx.channel.id]
    if s['valid']:
        scrim = s['scrim']
        e = discord.Embed(title="현재 스크림 정보", color=discord.Colour.orange())
        for t in scrim.team:
            e.add_field(
                name="팀 "+t,
                value='\n'.join(getusername(x) for x in scrim.team[t])
            )
        await ctx.send(embed=e)

####################################################################################################################

async def osu_login(session):
    async with session.get(OSU_HOME) as page:
        if page.status != 200:
            print(f'홈페이지 접속 실패 ({page.status})')
            print(page.raw_headers)
            await session.close()
            return False

        csrf = session.cookie_jar.filter_cookies(yarl.URL(OSU_HOME)).get('XSRF-TOKEN').value
        login_info = {**BASE_LOGIN_DATA, **{'_token': csrf}}

        async with session.post(OSU_SESSION, data=login_info, headers={'referer': OSU_HOME}) as req:
            if req.status != 200:
                print(f'로그인 실패 ({req.status})')
                await session.close()
                return False
            print('로그인 성공')
    return True

loop = asyncio.get_event_loop()
ses = aiohttp.ClientSession(loop=loop)
got_login = loop.run_until_complete(osu_login(ses))
if got_login:
    print('OSU LOGIN SUCCESS')
    turnoff = False
    try:
        api = OsuApi(api_key, connector=AHConnector())
        res = loop.run_until_complete(api.get_user("peppy"))
        assert res == 2
    except osuapi.errors.HTTPError:
        print("Invalid osu!API key")
        turnoff = True
    except AssertionError:
        print("Something went wrong")
        turnoff = True
    try:
        assert turnoff == False
        loop.run_until_complete(app.start(token))
    except KeyboardInterrupt:
        print("\nForce stop")
    except BaseException as ex:
        print(repr(ex))
        print(ex)
    finally:
        with open('uids.txt', 'w') as f:
            for u in uids:
                f.write(f"{u} {uids[u]}\n")
        with open('ratings.txt', 'w') as f:
            for u in ratings:
                f.write(f"{u} {ratings[u]}\n")
        api.close()
        loop.run_until_complete(app.logout())
        loop.run_until_complete(app.close())
        loop.run_until_complete(ses.close())
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.run_until_complete(asyncio.sleep(0.5))
        loop.close()
        print('Program Close')
else:
    print('OSU LOGIN FAILED')
