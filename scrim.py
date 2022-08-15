import fixca
from friend_import import *
from timer import Timer

if TYPE_CHECKING:
    from friend import MyBot
    from match import MatchScrim

class Scrim:
    __id = 0

    def __new__(cls, *args, **kwargs):
        instance = super().__new__(cls)
        instance.__id = cls.__id
        cls.__id += 1
        return instance

    def __init__(self,
                 bot: 'MyBot',
                 channel: discord.TextChannel,
                 match_: Optional['MatchScrim'] = None,
                 role: Optional[discord.Role] = None):
        self.bot = bot
        self.match = match_
        self.role = role
        self.loop = self.bot.loop
        self.channel: discord.TextChannel = channel
        self.start_time = datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')
        if self.match:
            if self.role is None:
                self.role = self.match.role
            if (mid := self.match.get_match_id()) == 'None':
                self.name = f"m_{self.match.get_id()}"
            else:
                self.name = f"m_{mid}"
        else :
            self.name = f"s{self.__id}"

        self.round_start_time = None
        self.round = 1

        self.match_task: Optional[asyncio.Task] = None

        self.team: Dict[str, Set[int]] = dict()
        # teamname : {member1_id, member2_id, ...}
        self.players: Set[int] = set()
        # {member1_id, member2_id, ...}
        self.findteam: Dict[int, str] = dict()
        # member_id : teamname
        self.setscore: Dict[str, int] = dict()
        # teamname : int
        self.score: Dict[int, Optional[dict]] = dict()
        # member_id : {score, acc, miss, grade, ...}
        self.uuids: Dict[int, str] = dict()
        self.playids: Dict[int, str] = dict()
        # member_id: datas
        
        self.map_artist: Optional[str] = None
        self.map_author: Optional[str] = None
        self.map_title: Optional[str] = None
        self.map_diff: Optional[str] = None
        self.map_length: Union[None, int, d] = None
        self.map_number: Optional[str] = None
        self.map_mode: Optional[str] = None
        self.map_hash: Optional[str] = None
        self.map_auto_score: Union[None, int, d] = None
        self.map_id: Optional[Tuple[int, int]] = None
        
        self.availablemode: Dict[str, Iterable[int]] = {
            'NM': {0, 2, },
            'HD': {16, 18, },
            'HR': {8, 10, },
            'DT': {32, 34, 48, 50},
            'FM': {1, 3, 8, 10, 16, 17, 18, 19, 24, 26},
            'TB': {0, 1, 2, 3, 8, 10, 16, 17, 18, 19, 24, 26}
        }

        self.setfuncs: Dict[str, Callable[[str], NoReturn]] = {
            'artist': self.setartist,
            'title' : self.settitle,
            'author': self.setauthor,
            'diff'  : self.setdiff,
            'number': self.setnumber,
            'mode'  : self.setmode,
            'autosc': self.setautoscore,
            'id'    : self.setmapid,
        }

        self.getfuncs: Dict[str, Callable[[], str]] = {
            'artist': self.getartist,
            'title' : self.gettitle,
            'author': self.getauthor,
            'diff'  : self.getdiff,
            'number': self.getnumber,
            'mode'  : self.getmode,
            'autosc': self.getautoscore,
            'id'    : self.getmapid,
        }

        self.log: IO = open(f'logs/{self.bot.user.name}_scrim_{self.name}_{self.start_time}.log', 'w', encoding='utf-8')
        init_text = f"[{get_nowtime_str()}] Scrim initiated.\n" \
                    f"Guild   : {self.channel.guild.name}\n" \
                    f"Channel : {self.channel.name}\n" \
                    f"Name    : {self.name}"
        print(init_text)
        self.write_log(init_text+"\n")
        self.timer: Optional[Timer] = None
        self.PRINT_ON: bool = True
        self.winning_log: List[List[AnyStr]] = []

    def __str__(self):
        return f"Scrim({self.name})"

    def __del__(self):
        if not self.log.closed:
            self.log.close()

    @classmethod
    def get_max_id(cls):
        return cls.__id

    def get_player_team(self, member: discord.Member):
        mid = member.id
        if mid not in self.players:
            return
        return self.findteam[mid]

    def write_log(self, s: AnyStr):
        if self.log.closed:
            with open(self.log.name, 'a', encoding='utf-8') as f_:
                f_.write(s)
        else:
            self.log.write(s)
            self.log.flush()

    async def maketeam(self, name: str, do_print: bool = None):
        if do_print is None:
            do_print = self.PRINT_ON
        if self.team.get(name) is not None and do_print:
            await self.channel.send(embed=discord.Embed(
                title=f"Team `{name}` already exists!",
                description=f"Now team list:"+''.join([f"\n`{s}`" for s in self.team.keys()]),
                color=discord.Colour.dark_blue()
            ))
        else:
            self.team[name] = set()
            self.setscore[name] = 0
            if do_print:
                await self.channel.send(embed=discord.Embed(
                    title=f"Added Team `{name}`.",
                    description=f"Now team list:"+''.join([f"\n`{s}`" for s in self.team.keys()]),
                    color=discord.Colour.blue()
                ))
            self.write_log(f"[{get_nowtime_str()}] Team \"{name}\" made.\n")

    async def removeteam(self, name: str, do_print: bool = None):
        if do_print is None:
            do_print = self.PRINT_ON
        if self.team.get(name) is None and do_print:
            await self.channel.send(embed=discord.Embed(
                title=f"There's no Team `{name}`.",
                description=f"Now team list:"+''.join([f"\n`{s}`" for s in self.team.keys()]),
                color=discord.Colour.dark_blue()
            ))
        else:
            for p in self.team[name]:
                del self.findteam[p]
            del self.team[name], self.setscore[name]
            if do_print:
                await self.channel.send(embed=discord.Embed(
                    title=f"Removed Team `{name}`.",
                    description=f"Now team list:"+''.join([f"\n`{s}`" for s in self.team.keys()]),
                    color=discord.Colour.blue()
                ))
            self.write_log(f"[{get_nowtime_str()}] Team \"{name}\" removed.\n")

    async def addplayer(self, name: str, member: Optional[discord.Member], do_print: bool=None):
        if do_print is None:
            do_print = self.PRINT_ON
        if not member:
            return
        mid = member.id
        temp = self.findteam.get(mid)
        if temp:
            if do_print:
                await self.channel.send(embed=discord.Embed(
                    title=f"Player `{member.display_name}` is already in Team `{temp}`!",
                    description=f"Please leave your team first (`//out`) and try again."
                ))
        elif self.team.get(name) is None:
            if do_print:
                await self.channel.send(embed=discord.Embed(
                    title=f"There's no Team `{name}`.",
                    description=f"Now team list:"+''.join([f"\n`{s}`" for s in self.team.keys()]),
                    color=discord.Colour.dark_blue()
                ))
        else:
            if mid not in self.uuids:
                userinfo = await self.bot.get_user_info(mid)
                if isinstance(userinfo, self.bot.req.ERRORS):
                    await self.channel.send(embed=discord.Embed(
                        title=f"Error occurred while loading `{member.display_name}`'(s) information.",
                        description=f"`{userinfo}`\nCheck the log."
                    ))
                    return
                self.uuids[mid] = (await self.bot.get_user_info(mid))['uuid']
            self.findteam[mid] = name
            self.team[name].add(mid)
            self.players.add(mid)
            self.score[mid] = {'score': d(0), 'acc': d(0), 'miss': d(0), 'rank': None, 'mode': 0}
            if do_print:
                await self.channel.send(embed=discord.Embed(
                    title=f"Player `{member.display_name}` participates into Team `{name}`!",
                    description=f"Now player list of Team `{name}`:"+
                                ''.join([f"\n`{self.bot.get_user(p).display_name}`" for p in self.team[name]]),
                    color=discord.Colour.blue()
                ))
            self.write_log(f"[{get_nowtime_str()}] Player \"{member.name}\" participated into Team {name}.\n")

    async def removeplayer(self, member: Optional[discord.Member], do_print: bool = None):
        if do_print is None:
            do_print = self.PRINT_ON
        if not member:
            return
        mid = member.id
        temp = self.findteam.get(mid)
        if mid not in self.players:
            if do_print:
                await self.channel.send(embed=discord.Embed(
                    title=f"Player `{member.display_name}` is participating in NO team!",
                    description=f"You participate first."
                ))
        else:
            del self.findteam[mid], self.score[mid]
            self.team[temp].remove(mid)
            self.players.remove(mid)
            if do_print:
                await self.channel.send(embed=discord.Embed(
                    title=f"Player `{member.display_name}` is leaving Team `{temp}`.",
                    description=f"Now player list of Team `{temp}`:" +
                                ''.join([f"\n`{self.bot.get_user(p).display_name}`" for p in self.team[temp]]),
                    color=discord.Colour.blue()
                ))
            self.write_log(f"[{get_nowtime_str()}] Player \"{member.name}\" left from Team {temp}.\n")

    async def addscore(self, 
                       member: Optional[discord.Member], 
                       score: int, acc: str, miss: int,
                       grade: str = None, mode: Union[int, str] = 0):
        if not member:
            return
        if type(mode) == str:
            mode = modetointfunc(re.findall(r'.{1,2}', mode, re.DOTALL))
        mid = member.id
        if mid not in self.players:
            await self.channel.send(embed=discord.Embed(
                title=f"Player `{member.display_name}` is participating in NO team!",
                description=f"You participate first."
            ))
        else:
            self.score[mid] = {'score': getd(score), 'acc': acc, 'miss': getd(miss), 'rank': grade, 'mode': mode}
            await self.channel.send(embed=discord.Embed(
                title=f"Player `{member.display_name}`'(s) score is modified.",
                description=f"Team `{self.findteam[mid]}` <== {score}, {acc}%, {miss}xMISS",
                color=discord.Colour.blue()
            ))
            self.write_log(f"[{get_nowtime_str()}] Player \"{member.name}\" added score.\n"
                           f"Score : {self.score[mid]['score']:,d}\n"
                           f"Acc   : {self.score[mid]['acc']}%\n"
                           f"Miss  : {self.score[mid]['miss']}\n"
                           f"Rank  : {self.score[mid]['rank']}\n"
                           f"Mode  : {inttomode(self.score[mid]['mode'])}\n")

    async def removescore(self, member: Optional[discord.Member], do_print: bool = None):
        if do_print is None:
            do_print = self.PRINT_ON
        if not member:
            return
        mid = member.id
        if mid not in self.players and do_print:
            await self.channel.send(embed=discord.Embed(
                title=f"Player `{member.display_name}` is participating in NO team!",
                description=f"You participate first."
            ))
        else:
            self.score[mid] = {'score': getd(0), 'acc': "00.00", 'miss': getd(0), 'rank': None, 'mode': 0}
            await self.channel.send(embed=discord.Embed(
                title=f"Player `{member.display_name}`'(s) score is deleted.",
                color=discord.Colour.blue()
            ))
            self.write_log(f"[{get_nowtime_str()}] Player \"{member.name}\" removed score.\n")
    
    async def submit(self, calcmode: Optional[str] = None):
        if v2dict.get(calcmode) is None:
            await self.channel.send(embed=discord.Embed(
                title="Unknown Calculate Mode!",
                description="It should be (Empty), `nero2`, `jet2`, or `osu2`"
            ))
            return
        elif calcmode and (self.getautoscore() == -1):
            await self.channel.send(embed=discord.Embed(
                title="Autoplay score is needed to calculate V2-kind score!",
                description="Modify it by using `m;mapscore`."
            ))
            return
        self.write_log(f"[{get_nowtime_str()}] Submit running... (calcmode : {calcmode})\n")
        calcf = v2dict[calcmode]
        resultmessage = await self.channel.send(embed=discord.Embed(
            title="Calculating...",
            color=discord.Colour.orange()
        ))
        calculatedscores = dict()
        for p in self.score:
            calculatedscores[p] = calcf(
                self.map_auto_score, 
                self.score[p]['score'],
                self.score[p]['acc'],
                self.score[p]['miss']
            )
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
            title="========= ! ROUND END ! =========",
            description=f"__**Team `{desc}` get(s) a point!**__",
            color=discord.Colour.red()
        )
        sendtxt.add_field(
            name="Map Info",
            value='`'+self.getmapfull()+'`',
            inline=False
        )
        sendtxt.add_field(
            name="Map Number",
            value=self.getnumber(),
            inline=False
        )
        sendtxt.add_field(
            name=blank,
            value='='*20+'\n'+blank,
            inline=False
        )
        logtxt = [
            f'Map         : {self.getmapfull()}\n',
            f'Map mode    : {self.getnumber()}\n',
            f'CalcFormula : {calcmode if calcmode else "V1"}\n',
            f'Winner Team : {desc}\n\n'
        ]
        for lt in logtxt:
            self.write_log(lt)
        for t in teamscore:
            self.write_log(f"Team {t} : {teamscore[t]}\n")
            temptxt = ""
            for p in self.team[t]:
                temptxt += f"{await self.bot.get_discord_username(p)} - {self.bot.RANK_EMOJI[self.score[p]['rank']]} " \
                           f"({inttomode(self.score[p]['mode'])}) : " \
                           f"{self.score[p]['score']} / {self.score[p]['acc']}% / {self.score[p]['miss']} :x:" + \
                           (f" = {calculatedscores[p]}" if calcmode is not None else "") + "\n"
            sendtxt.add_field(
                name=f"*Team `{t}` total score : {teamscore[t]}*",
                value=temptxt,
                inline=False
            )
            self.write_log(temptxt+'\n')
        sendtxt.add_field(
            name=blank,
            value='='*20+'\n'+blank,
            inline=False
        )
        sendtxt.add_field(
            name="__Now team score:__",
            value='\n'.join([f"**`{t}` : {self.setscore[t]}**" for t in teamscore]),
            inline=False
        )
        self.write_log("Team score:\n")
        for t in teamscore:
            self.write_log(f"{t} : {self.setscore[t]}\n")
        await resultmessage.edit(embed=sendtxt)
        self.write_log(f"[{get_nowtime_str()}] Submit finished.\n")
        self.round += 1
        return winnerteam
    
    async def submit_fixca(self):
        self.write_log(f"[{get_nowtime_str()}] Submit running... (calcmode : FIXCA)\n")
        resultmessage = await self.channel.send(embed=discord.Embed(
            title="Calculating...",
            color=discord.Colour.orange()
        ))
        teamscore = dict()
        for t in self.team:
            teamscore[t] = 0
            for p in self.team[t]:
                teamscore[t] += self.score[p]['score']
        winnerteam = list(filter(
            lambda x: teamscore[x] == max(teamscore.values()),
            teamscore.keys()
        ))
        for w in winnerteam:
            self.setscore[w] += 1
        desc = ', '.join('"'+t+'"' for t in winnerteam)
        sendtxt = discord.Embed(
            title="========= ! ROUND END ! =========",
            description=f"__**Team `{desc}` get(s) a point!**__",
            color=discord.Colour.red()
        )
        sendtxt.add_field(
            name="Map Info",
            value='`'+self.getmapfull()+'`',
            inline=False
        )
        if self.match:
            sendtxt.add_field(
                name="Map Number",
                value=self.getnumber(),
                inline=False
            )
        else:
            sendtxt.add_field(
                name="Map Mode",
                value=self.getmode(),
                inline=False
            )
        sendtxt.add_field(
            name=blank,
            value='='*20+'\n'+blank,
            inline=False
        )
        logtxt = [
            f'Map         : {self.getmapfull()}\n',
            f'Map mode    : {self.getnumber() if self.match else self.getmode()}\n',
            f'MapNick     : {self.map_number}\n',
            f'CalcFormula : FIXCA\n',
            f'Winner Team : {desc}\n\n'
        ]
        for lt in logtxt:
            self.write_log(lt)
        for t in teamscore:
            self.write_log(f"Team {t} : {teamscore[t]}\n")
            temptxt = ""
            for p in self.team[t]:
                temptxt += f"{await self.bot.get_discord_username(p)} - {self.bot.RANK_EMOJI[self.score[p]['rank']]} " \
                           f"({inttomode(self.score[p]['mode'])}) : " \
                           f"{self.score[p]['score']} / {self.score[p]['acc']}% / {self.score[p]['miss']} :x:\n" \
                           f"({self.score[p].get('300')}, {self.score[p].get('100')}, {self.score[p].get('50')})" \
                           + "\n"
            sendtxt.add_field(
                name=f"*Team `{t}` total score : {teamscore[t]}*",
                value=temptxt,
                inline=False
            )
            self.write_log(temptxt+'\n')
        sendtxt.add_field(
            name=blank,
            value='='*20+'\n'+blank,
            inline=False
        )
        sendtxt.add_field(
            name="__Now team score:__",
            value='\n'.join([f"**`{t}` : {self.setscore[t]}**" for t in teamscore]),
            inline=False
        )
        self.write_log("Team score:\n")
        for t in teamscore:
            self.write_log(f"{t} : {self.setscore[t]}\n")
        await resultmessage.edit(embed=sendtxt)
        self.write_log(f"[{get_nowtime_str()}] Submit finished.\n")
        self.round += 1
        return winnerteam
    
    def resetmap(self):
        self.map_artist = None
        self.map_author = None
        self.map_title = None
        self.map_diff = None
        self.map_number = None
        self.map_mode = None
        self.map_auto_score = None
        self.map_length = None
        self.map_hash = None
        for p in self.score:
            self.score[p] = {'score': d(0), 'acc': "00.00", 'miss': d(0), 'rank': None, 'mode': 0}
        self.round_start_time = None
        self.write_log(f"[{get_nowtime_str()}] Map reset.\n")
    
    def setartist(self, artist: str):
        self.map_artist = artist
        self.write_log(f"[{get_nowtime_str()}] Map modified: artist => {artist}\n")

    def getartist(self) -> str:
        return self.map_artist if self.map_artist is not None else ''

    def settitle(self, title: str):
        self.map_title = title
        self.write_log(f"[{get_nowtime_str()}] Map modified: title => {title}\n")

    def gettitle(self) -> str:
        return self.map_title if self.map_title is not None else ''

    def setauthor(self, author: str):
        self.map_author = author
        self.write_log(f"[{get_nowtime_str()}] Map modified: author => {author}\n")

    def getauthor(self) -> str:
        return self.map_author if self.map_author is not None else ''

    def setdiff(self, diff: str):
        self.map_diff = diff
        self.write_log(f"[{get_nowtime_str()}] Map modified: diff => {diff}\n")

    def getdiff(self) -> str:
        return self.map_diff if self.map_diff is not None else ''

    def setnumber(self, number: str):
        self.map_number = number
        self.write_log(f"[{get_nowtime_str()}] Map modified: number => {number}\n")

    def getnumber(self) -> str:
        return self.map_number if self.map_number is not None else '-'

    def setmode(self, mode: str):
        self.map_mode = mode
        self.write_log(f"[{get_nowtime_str()}] Map modified: mode => {mode}\n")

    def getmode(self) -> str:
        return self.map_mode if self.map_mode is not None else '-'

    def setautoscore(self, score: Union[int, d]):
        self.map_auto_score = score
        self.write_log(f"[{get_nowtime_str()}] Map modified: auto_score => {score}\n")

    def getautoscore(self) -> Union[int, d]:
        return self.map_auto_score if self.map_auto_score is not None else -1

    def setmaplength(self, t: Union[int, d]):
        self.map_length = t
        self.write_log(f"[{get_nowtime_str()}] Map modified: length => {t}\n")

    def getmaplength(self) -> Union[int, d]:
        return self.map_length if self.map_length is not None else -1

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

    def setmaphash(self, h: str):
        self.map_hash = h
        self.write_log(f"[{get_nowtime_str()}] Map modified: hash => {h}\n")

    def getmaphash(self) -> str:
        return self.map_hash if self.map_hash is not None else 'Undefined'
    
    def setmapid(self, mapid, mapsetid):
        self.map_id = (mapid, mapsetid)
        self.write_log(f"[{get_nowtime_str()}] Map modified: ID => {mapid}, {mapsetid}\n")
    
    def getmapid(self):
        return self.map_id if self.map_id is not None else (0, 0)
    
    def setmoderule(
            self,
            nm: Optional[Iterable[int]],
            hd: Optional[Iterable[int]],
            hr: Optional[Iterable[int]],
            dt: Optional[Iterable[int]],
            fm: Optional[Iterable[int]],
            tb: Optional[Iterable[int]]
    ):
        if nm or hd or hr or dt or fm or tb:
            self.write_log(f"[{get_nowtime_str()}] Map modified: rule\n")
        if nm:
            self.availablemode['NM'] = nm
            self.write_log(f"NM : {nm}\n")
        if hd:
            self.availablemode['HD'] = hd
            self.write_log(f"HD : {hd}\n")
        if hr:
            self.availablemode['HR'] = hr
            self.write_log(f"HR : {hr}\n")
        if dt:
            self.availablemode['DT'] = dt
            self.write_log(f"DT : {dt}\n")
        if fm:
            self.availablemode['FM'] = fm
            self.write_log(f"FM : {fm}\n")
        if tb:
            self.availablemode['TB'] = tb
            self.write_log(f"TB : {tb}\n")

    async def set_map_from_id(self, map_id: int, beatmap_obj: 'osuapi.osu.Beatmap' = None):
        if not beatmap_obj:
            search_result = await self.bot.osuapi.get_beatmaps(beatmap_id=map_id)
            if len(search_result) > 1:
                raise ValueError(f"Multiple maps searched for beatmap id {map_id}")
            elif not search_result:
                raise ValueError(f"No beatmaps found for beatmap id {map_id}")
            beatmap_obj = search_result[0]
        self.setartist(beatmap_obj.artist)
        self.setauthor(beatmap_obj.creator)
        self.settitle(beatmap_obj.title)
        self.setdiff(beatmap_obj.version)
        self.setmaplength(beatmap_obj.total_length)
        self.setmapid(beatmap_obj.beatmap_id, beatmap_obj.beatmapset_id)
        self.setmaphash(beatmap_obj.file_md5)

    async def create_play_id(self):
        mapid = self.getmapid()[0]
        for p in self.players:
            playid_obj = await self.bot.req.create_playID(self.uuids[p], mapid)
            if isinstance(playid_obj, self.bot.req.ERRORS):
                pname = self.bot.get_user(p).display_name
                await self.channel.send(embed=discord.Embed(
                    title=f"Error occured while creating play ID of `{pname}`.",
                    description=f"`{playid_obj}`\nCheck the log.\n`{pname}`'(s) record will not be submitted."
                ))
                continue
            self.playids[p] = (await self.bot.req.create_playID(self.uuids[p], mapid))['playId']

    async def expire_play_id(self):
        for p in self.players:
            temp = await self.bot.req.expire_playid(self.playids[p])
            if isinstance(temp, self.bot.req.ERRORS):
                if temp.data['code'] == fixca.FixcaErrorCode.EXPIRED_PLAYID:
                    continue
                pname = self.bot.get_user(p).display_name
                await self.channel.send(embed=discord.Embed(
                    title=f"Error occured while expiring play ID of `{pname}`.",
                    description=f"`{temp}`\nCheck the log.\nIt may have to be get expired manually."
                ))

    async def onlineload(self):
        self.write_log(f"[{get_nowtime_str()}] Onlineload running...\n")
        desc = '====== < Process LOG > ======'
        resultmessage: discord.Message = await self.channel.send(embed=discord.Embed(
            title="Processing...",
            color=discord.Colour.red()
        ))
        for team in self.team:
            for player in self.team[team]:
                desc += '\n'
                playername = await self.bot.get_discord_username(player)
                await resultmessage.edit(embed=discord.Embed(
                    title="Processing...",
                    description=desc,
                    color=discord.Colour.orange()
                ))
                if self.match:
                    player_recent_info = await self.bot.get_recent(
                        id_=self.match.uuid[player])
                else:
                    uuid_ = await self.bot.get_user_info(player)
                    if isinstance(uuid_, self.bot.req.ERRORS):
                        temptxt = f":x: | `{playername}` - " \
                                  f"Error occurred while getting user info. (`{uuid_}`)"
                        desc += temptxt
                        self.write_log(temptxt+"\n")
                        continue
                    player_recent_info = await self.bot.get_recent(
                        id_=uuid_['uuid'])
                if isinstance(player_recent_info, self.bot.req.ERRORS):
                    if player_recent_info.data['code'] == fixca.FixcaErrorCode.PLAYER_NO_RECORDS:
                        temptxt = f":x: | `{playername}` - " \
                                  f"Didn't play the map."
                        desc += temptxt
                        self.write_log(temptxt+"\n")
                    else:
                        temptxt = f":x: | `{playername}` - " \
                                  f"Error occurred while getting recent record. (`{player_recent_info}`)"
                        desc += temptxt
                        self.write_log(temptxt+"\n")
                    continue
                if player_recent_info is None:
                    temptxt = f":x: | `{playername}` - " \
                              f"Your recent play info can't be parsed."
                    desc += temptxt
                    self.write_log(temptxt+"\n")
                    continue
                if player_recent_info['mapHash'] != self.getmaphash():
                    temptxt = f":x: | `{playername}` - " \
                              f"Wrong hash.\n(Map : `{self.getmaphash()}` / You : `{player_recent_info['mapHash']}`)"
                    desc += temptxt
                    self.write_log(temptxt+"\n")
                    continue
                modeint = modetointfunc(re.findall(r'.{1,2}', player_recent_info['modList'], re.DOTALL))
                if self.map_mode is not None and \
                    modeint not in self.availablemode[self.map_mode]:
                    temptxt = f":x: | `{playername}` - " \
                              f"Not allowed mode." \
                              f"(Allowed : `{self.availablemode[self.map_mode]}` / " \
                              f"You : `{player_recent_info['modList']} = {modeint}`)"
                    desc += temptxt
                    self.write_log(temptxt+"\n")
                    continue
                self.score[player] = player_recent_info
                self.score[player]['score'] = d(self.score[player]['score'])
                if self.map_mode == 'FM' and (modeint == 0 or modeint == 128):
                    self.score[player]['score'] *= d('.8')
                self.score[player]['acc'] = d(self.score[player]['acc'][:-1])
                self.score[player]['miss'] = d(self.score[player]['miss'])
                self.score[player]['mode'] = modeint
                temptxt = f":white_check_mark: | `{playername}` = " \
                          f"{self.score[player]['score']}, {self.score[player]['acc']}%, " \
                          f"{self.score[player]['miss']} MISS(es) / " \
                          f"{self.score[player]['modList']} / {self.score[player]['rank']} rank"
                desc += temptxt
                self.write_log(temptxt+"\n")
        await resultmessage.edit(embed=discord.Embed(
            title="Calculation finished!",
            description=desc,
            color=discord.Colour.green()
        ))
        self.write_log(f"[{get_nowtime_str()}] Onlineload finished.\n")

    async def end(self):
        winnerteam = list(filter(
            lambda x: self.setscore[x] == max(self.setscore.values()),
            self.setscore.keys()
        ))
        sendtxt = discord.Embed(
            title="========= ! MATCH END ! =========",
            description="Team " + ', '.join(f"\"{w}\"" for w in winnerteam) + " WON!",
            color=discord.Colour.magenta()
        )
        sendtxt.add_field(
            name=blank,
            value='='*20+'\n'+blank,
            inline=False
        )
        sendtxt.add_field(
            name="THE RESULT:",
            value=blank + '\n'.join(f"`{t}` : {self.setscore[t]}" for t in self.setscore)
        )
        sendtxt.add_field(
            name=blank,
            value='='*20+'\n'+blank,
            inline=False
        )
        sendtxt.add_field(
            name="GGWP! Thank you for the match!",
            value='The match will be reset.\n'
                  'You can download this file and see the match logs.',
            inline=False
        )
        self.write_log(f"[{get_nowtime_str()}] Scrim END\n"
                       f"Team score:\n")
        for t in self.setscore:
            self.write_log(f"{t} : {self.setscore[t]}\n")
        self.log.close()
        with open(self.log.name, 'rb') as fp_:
            await self.channel.send(
                embed=sendtxt,
                file=discord.File(fp_)
            )
        print(f"[{get_nowtime_str()}] {self}.end(): Scrim finished.")
        if self.match is None:
            async def callback(*args):
                await self.role.delete()
                await self.channel.delete()
            Timer(self.bot, self.channel, f"{self.name}_delete", 120, callback)
        return winnerteam
        
    async def do_match_start(self):
        if self.match_task is None or self.match_task.done():
            self.match_task = self.loop.create_task(self.match_start())
        else:
            await self.channel.send(embed=discord.Embed(
                title="Match is already processing!",
                description="Try again after the match ends.",
                color=discord.Colour.dark_red()
            ))

    async def match_start(self):
        self.write_log(f"[{get_nowtime_str()}] match_start running...\n")
        try:
            if self.map_length is None:
                await self.channel.send(embed=discord.Embed(
                    title="The length of the map is not modified!",
                    description="Use `//maptime` and try again.",
                    color=discord.Colour.dark_red()
                ))
                self.write_log(f"[{get_nowtime_str()}] match_start(): Map time not set.\n")
                return
            try:
                self.round_start_time = int(time.time())
                await asyncio.gather(self.channel.send(embed=discord.Embed(
                    title=f"Round #{self.round} START!",
                    description=f"Map Info : `{self.getmapfull()}`\n"
                                f"{'Map Number : {self.getnumber()} / ' if self.match else ''}Map Mode : {self.getmode()}\n"
                                f"Map Length : {self.getmaplength()} sec\n"
                                f"Allowed modes : "
                                f"`{', '.join(map(inttomode, self.availablemode[self.getmode()]))}`",
                    color=discord.Colour.from_rgb(255, 255, 0)
                )), self.create_play_id())
                extra_rate = d('1')
                if self.getmode() == 'DT':
                    extra_rate = d('1') / d('1.5')
                self.timer = Timer(self.bot, self.channel, f"{self.name}_{self.round}_{self.getnumber()}",
                                   int(self.getmaplength() * extra_rate))
                self.write_log(f"[{get_nowtime_str()}] match_start(): "
                               f"Waiting until map finish... ({self.timer.seconds} seconds)\n")
                await self.timer.task
                timermessage = await self.channel.send(embed=discord.Embed(
                    title=f"MAP TIME OVER!",
                    color=discord.Colour.from_rgb(128, 128, 255)
                ))
                self.write_log(f"[{get_nowtime_str()}] match_start(): "
                               f"Map finished. Waiting more 30 seconds...\n")
                self.timer = Timer(self.bot, self.channel, f"{self.name}_{self.round}_extra", 30)
                await self.timer.task
                await self.channel.send(embed=discord.Embed(
                    title=f"MAP EXTRA TIME OVER!",
                    description="Online loading...",
                    color=discord.Colour.from_rgb(128, 128, 255)
                ))
                self.write_log(f"[{get_nowtime_str()}] match_start(): "
                               f"ALL done, onlineload() calling...\n")
                await self.onlineload()
                self.write_log(f"[{get_nowtime_str()}] match_start(): "
                               f"onlineload() done, submit() calling...\n")
                w = await self.submit_fixca()
                self.write_log(f"[{get_nowtime_str()}] match_start(): "
                               f"submit() done.\n")
                self.winning_log.append(w)
                if self.match is not None and not self.match.is_duel:
                    response = await self.bot.req.upload_record(self.match)
                    if isinstance(response, self.bot.req.ERRORS):
                        self.write_log(self.bot.req.censor(str(response.data)) + '\n')
                        raise response
                    assert response['redScore'] == self.setscore["RED"]
                    assert response['blueScore'] == self.setscore["BLUE"]
                self.resetmap()
                await self.expire_play_id()
            except asyncio.CancelledError:
                await self.channel.send(embed=discord.Embed(
                    title="Match Aborted!",
                    color=discord.Colour.dark_red()
                ))
                self.write_log(f"[{get_nowtime_str()}] match_start(): aborted.\n")
                raise
            except GeneratorExit:
                return
        except BaseException as ex_:
            print(f'[{get_nowtime_str()}] {self}.match_start() :')
            print(get_traceback_str(ex_))
            raise ex_

