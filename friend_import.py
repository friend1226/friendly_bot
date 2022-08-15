import asyncio, aiohttp, \
    datetime, decimal, discord, random, re, time, \
    traceback, scoreCalc, os, json, bisect, hashlib, osuapi, io, sys
# import logging
from typing import *
from collections import defaultdict as dd
from collections import deque
from discord.ext import commands, tasks
from enum import IntEnum

"""
from bs4 import BeautifulSoup
from google.oauth2.service_account import Credentials

from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive
"""
BOT_DEBUG = True
"""
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
drive_cred = 'credentials.json'
gauth.LoadCredentialsFile(drive_cred)
if gauth.credentials is None:
    gauth.LocalWebserverAuth()
elif gauth.access_token_expired:
    gauth.Refresh()
else:
    gauth.Authorize()
gauth.SaveCredentialsFile(drive_cred)
drive = GoogleDrive(gauth)

drive_folder = drive.ListFile(
    {'q': "title='od' and mimeType='application/vnd.google-apps.folder' and trashed=false"}
).GetList()[0]
"""
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.reactions = True

d = decimal.Decimal

def ftod(n: Union[int, float]):
    return d(str(n))

with open("key.txt", 'r') as f:
    token = f.read().strip()
"""
with open("osu_login.json", 'r') as f:
    BASE_LOGIN_DATA = json.load(f)

"""
with open("osu_api_key.txt", 'r') as f:
    api_key = f.read().strip()

with open("oma_pools.json", 'r', encoding='utf-8-sig') as f:
    maidbot_pools = json.load(f, parse_float=d)

def get_traceback_str(exception):
    return ''.join(traceback.format_exception(type(exception), exception, exception.__traceback__)).strip()

url_base = "http://ops.dgsrz.com/profile.php?uid="
search_url_base = "http://ops.dgsrz.com/challenge_profile_en.php?=search"
mapr = re.compile(r"(.*?) [-] ([^\[]*) [(](.*?)[)] [\[](.*)[]]")
playr = re.compile(r"(.*) / (.*) / (.*) / (.*)x / (.*)%")
missr = re.compile(r"[{]\"miss\":(\d+), \"hash\":(.*)[}]")


async def getrecent(self, _id: int) -> Optional[Tuple[Sequence[AnyStr], Sequence[AnyStr], Sequence[AnyStr], str]]:
    from bs4 import BeautifulSoup
    url = url_base + str(_id)
    html = await self.session.get(url)
    bs = BeautifulSoup(await html.text(), "html.parser")
    recent = bs.select_one("#activity > ul > li:nth-child(1)")
    recent_mapinfo = recent.select("a.clear > strong.block")[0].text
    recent_playinfo = recent.select("a.clear > small")[0].text
    recent_miss = recent.select("#statics")[0].text
    rank_img_filename = recent.select("a.thumb-sm.pull-left.m-r-sm > img")[0]['src']
    rmimatch = mapr.match(recent_mapinfo)
    if rmimatch is None:
        return None
    return (rmimatch.groups(),
            playr.match(recent_playinfo).groups(),
            missr.match(recent_miss).groups(),
            rank_img_filename)

OSU_HOME = "https://osu.ppy.sh/home"
OSU_SESSION = "https://osu.ppy.sh/session"
OSU_BEATMAP_BASEURL = "https://osu.ppy.sh/beatmapsets/"

CHIMU = "https://api.chimu.moe/v1/download/"
chimu_params = {'n': '1'}

BEATCONNECT = "https://beatconnect.io/b/"

# logging.basicConfig(
#     filename=f"{datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')}.log",
#     encoding='utf-8'
# )

downloadpath = os.path.join('songs', '%s.zip')

prohibitted = re.compile(r"[\\/:*?\"<>|]")
multi_spaces_remover = re.compile(r"[ ]+")

parse_fixca = re.compile(r"Various Artists - Ranked Osu!droid Match #\d+ \(Various Mappers\) "
                         r"\[\[(.*?)] (.*) - (.*)\((.*)\)][.]osu")

KST = datetime.timezone(datetime.timedelta(hours=9))
shutdown_time = datetime.time(4, 0, tzinfo=KST)

def get_shutdown_datetime():
    shutdown_datetime = datetime.datetime.now(tz=KST)
    if shutdown_datetime.timetz() > shutdown_time:
        shutdown_datetime += datetime.timedelta(days=1)
    shutdown_datetime = shutdown_datetime.replace(
        hour=shutdown_time.hour,
        minute=shutdown_time.minute,
        second=shutdown_time.second,
        microsecond=shutdown_time.microsecond
    )
    return shutdown_datetime

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

analyze = re.compile(r"(?P<artist>.*) [-] (?P<title>.*) [(](?P<author>.*)[)] \[(?P<diff>.*)]")

def makefull(**kwargs: str):
    return f"{kwargs['artist']} - {kwargs['title']} ({kwargs['author']}) [{kwargs['diff']}]"

def dice(s: str):
    s = s.partition('d')
    if s[1] == '':
        return None
    return tuple(str(random.randint(1, int(s[2]))) for _ in range(int(s[0])))

RANKED_OSUDROID_GUILD_ID = 823413857036402739
TEST_GUILD_ID = 637659003735900161

def is_owner():
    async def predicate(ctx):
        roleids = {r.id for r in ctx.author.roles}
        return 823414751689441331 in roleids or 829370083653713971 in roleids or ctx.author.id == 327835849142173696 \
               or ctx.author.id == 341785408931233793  # fixca
    return commands.check(predicate)

def is_verified():
    async def predicate(ctx):
        return 823415179177885706 in {r.id for r in ctx.author.roles} or ctx.guild.id == TEST_GUILD_ID
    return commands.check(predicate)

def is_queue_channel():
    async def predicate(ctx):
        return (ctx.guild.id == RANKED_OSUDROID_GUILD_ID and
                ctx.channel.id in {823459553529692200, 829369406487265302, 824986021539741747}) or \
               (ctx.guild.id == TEST_GUILD_ID)
    return commands.check(predicate)

visibleinfo = ['artist', 'title', 'author', 'diff']
modes = ['NM', 'HD', 'HR', 'DT', 'FM', 'TB']
moder = re.compile(r"(NM|HD|HR|DT|FM|TB)")
modetoint = {
    'NM': 0,
    'EZ': 1,
    'NF': 2,
    'HF': 4,
    'HR': 8,
    'HD': 16,
    'DT': 32,
    'NC': 64,
    'PR': 128,
    'FL': 256,
}
modeabbrev = {
    'None': 'NM',
    'Easy': 'EZ',
    'NoFail': 'NF',
    'HalfTime': 'HF',
    'HardRock': 'HR',
    'Hidden': 'HD',
    'DoubleTime': 'DT',
    'NightCore': 'NC',
    'Precise': 'PR',
    'FlashLight': 'FL',
}
infotoint = {
    'artist': 1,
    'title': 2,
    'author': 4,
    'diff': 8,
    'mode': 16
}

def modetointfunc(_modes: Iterable[str]) -> int:
    r = 0
    for md in _modes:
        if modeabbrev.get(md):
            md = modeabbrev[md]
        if modetoint.get(md):
            r |= modetoint[md]
    return r

def inttomode(i: Optional[int], sep: str = '') -> str:
    if i:
        r = []
        for md in modeabbrev.values():
            if i & modetoint[md]:
                r.append(md)
        return sep.join(r)
    elif i is None:
        return 'N/A'
    else:
        return 'NM'
"""
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
"""
class BotOff(Exception):
    def __init__(self):
        super().__init__("Shutdown is coming!")

async def auto_off(shutdown_datetime):
    try:
        life_time = (shutdown_datetime - datetime.datetime.now(KST)).total_seconds()
        print(f'[@] Shutdown after {life_time} second(s).')
        await asyncio.sleep(life_time)
        raise BotOff()
    except asyncio.CancelledError:
        return
    except BotOff:
        raise

RANK_EMOJI = {
    'A': "<:rankingA:924468249578577980>",
    'B': "<:rankingB:924468249607934013>",
    'C': "<:rankingC:924468249679253534>",
    'D': "<:rankingD:924468249549226015>",
    'S': "<:rankingS:924468249675063328>",
    'SH': "<:rankingSH:924468249339498557>",
    'X': "<:rankingX:924468249620525147>",
    'XH': "<:rankingXH:924468249763147846>",
    None: ":question:"
}

rankFilenameR = re.compile('assets/images/ranking-(.+)-small[.]png')

ELO_RANK_NAMES = ['Bronze', 'Silver', 'Gold', 'Platinum', 'Diamond', 'Master']
ELO_RANK_SCORE_BOUNDARY = [1500, 1800, 2100, 2500, 3000]
ELO_INITIAL_RANK_BOUNDARY = [0, 100, 300, 700, 1500, 6500]
ELO_INITIAL_RANK_RATE = [d('2'), d('1'), d('.5'), d('.25'), d('.04')]

def get_elo_rank(elov: Union[d, int]):
    return ELO_RANK_NAMES[bisect.bisect(ELO_RANK_SCORE_BOUNDARY, elov)]

def get_initial_elo(rank: Union[d, int]):
    idx = bisect.bisect_left(ELO_INITIAL_RANK_BOUNDARY, rank) - 1
    if idx == 5:
        return d('1000')
    else:
        rate = ELO_INITIAL_RANK_RATE[idx]
        return d('2000') - d('200') * idx - rate * (rank - ELO_INITIAL_RANK_BOUNDARY[idx])

ELO_K = 50
ELO_STDV = 2500

ELO_RANK_ENTRY_COST = [-10, -5, 0, 5, 10, 15]

def get_elo_rank_entry_cost(elov: Union[d, int]):
    return ELO_RANK_ENTRY_COST[bisect.bisect(ELO_RANK_SCORE_BOUNDARY, elov)]

ELO_MID_RATING = d('1500')

SELECT_POOL_RANGE = 150
SELECT_POOL_LOWEST = 1200
SELECT_POOL_HIGHEST = 3300

def elo_convert(x):
    return (x - 1000) * d('2.1') + 1200

def elo_convert_rev(x):
    return (x - 1200) / d('2.1') + 1000

unplayable_pools_uuid = {
    "462ef3b6-b4ed-3331-96fd-b5c61aa9187c",
    "7cdd9393-1bfa-3f40-a430-563abd9009a4",
    "578c649c-fd05-3945-9af8-29d282fa2fc0",
    "1a35a1b2-f118-32d6-9449-fd19c97737f4",
}

TIER_IMAGES = {
    "Bronze": 'images/bronze.png',
    "Silver": 'images/silver.png',
    "Gold": 'images/gold.png',
    "Platinum": 'images/platinum.png',
    "Diamond": 'images/diamond.png',
    "Master": 'images/master.png',
}


class Tee(object):
    def __init__(self, name, mode):
        self.file = open(name, mode, encoding='utf-8')
        self.stdout = sys.stdout
        sys.stdout = self

    def __del__(self):
        sys.stdout = self.stdout
        self.file.close()

    def write(self, data):
        if not self.file.closed:
            self.file.write(data)
            self.flush()
        self.stdout.write(data)

    def flush(self):
        if not self.file.closed:
            self.file.flush()


def elo_show_form(el: d):
    return f"{el.quantize(d('.001'), rounding=decimal.ROUND_FLOOR):,.4f}"

TIMEFORMAT = '%Y-%m-%d %X.%f'

def get_nowtime_str():
    return datetime.datetime.utcnow().strftime(TIMEFORMAT)[:-3]

DISCORD_STATS = [
    discord.Status.online,
    discord.Status.offline,
    discord.Status.idle,
    discord.Status.dnd
]
