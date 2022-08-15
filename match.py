import fixca
from friend_import import *
from scrim import Scrim
from timer import Timer
from elo_rating import EloRating

if TYPE_CHECKING:
    from friend import MyBot

"""
oma_pools.json
each mappool has this dict
{
    "version": 6,
    "name": "Lobby 42: Random Team Tournament Grand Finals",
    "averageMMR": 2084.831101253304,
    "maps": [
      {
        "mapId": 1618099,
        "mod": "NOMOD",
        "mapName": "Shinra-bansho - Itazura Sensation",
        "difficultyName": "Shira's Lunatic",
        "length": 259,
        "starRating": 6.00795,
        "mapSetId": 745460,
        "maxCombo": 1381,
        "bpm": 192,
        "downloadAvailable": true,
        "mmr": 0,
        "skillset": "NOT_DEFINED",
        "sheetId": "NM1"
      },
      ...
    ],
    "ranked": true,
    "canBeRandomlySelected": true,
    "gamemode": "OSU",
    "uuid": "5ac418ae-0fee-3855-ab8d-8846d7776af2"
}
"""


class MatchScrim:
    __id = 0

    def __init__(self,
                 bot: 'MyBot',
                 player: discord.Member,
                 opponent: discord.Member,
                 bo: int = 7,
                 duel: Optional[Union[int, d, str]] = None):
        self.bot = bot
        self.player = player
        self.opponent = opponent
        self.player_info = None
        self.opponent_info = None
        self.BO = bo
        self.__id = MatchScrim.__id
        MatchScrim.__id += 1
        self.channel: Optional[discord.TextChannel] = None
        self.made_time = datetime.datetime.utcnow()
        self.playID: Dict[int, Optional[dict]] = {self.player.id: None, self.opponent.id: None}
        self.uuid: Dict[int, Optional[str]] = {self.player.id: None, self.opponent.id: None}

        self.mappool_uuid: Optional[str] = None
        self.mappool_info: Optional[dict] = None
        self.map_infos: Dict[str, osuapi.osu.Beatmap] = dict()
        self.map_order: List[str] = []
        self.map_tb: Optional[str] = None
        self.match_id: Optional[str] = None

        self.scrim: Optional[Scrim] = None
        self.role: Optional[discord.Role] = None
        self.timer: Optional[Timer] = None

        self.round = -1
        # -1 = 매치 생성 전
        # 0 = 플레이어 참가 대기
        # n = n라운드 준비 대기
        self.winfor = (bo / d('2')).to_integral(rounding=decimal.ROUND_HALF_UP)
        self.match_end = False
        self.aborted = False

        self.elo_manager = EloRating(k=ELO_K, stdv=ELO_STDV)

        self.player_ready: bool = False
        self.opponent_ready: bool = False

        self.match_task: Optional[asyncio.Task] = None
        self.readyable: bool = False

        self.is_duel = duel is not None
        self.duel_mappool_targ = duel if self.is_duel and duel != 'None' else None

    def __str__(self):
        return f"Match_{self.get_match_id()}({self.player.name}, {self.opponent.name})"

    def __repr__(self):
        return f"MatchScrim(ID={self.get_id()})({self.player}, {self.opponent})"

    def get_id(self):
        return self.__id
    
    def get_match_id(self):
        return self.match_id

    @classmethod
    def get_max_id(cls):
        return cls.__id

    def get_debug_txt(self):
        if self.match_task.exception() is not None:
            return get_traceback_str(self.match_task.exception())

    async def switch_ready(self, subj):
        if not self.readyable: return
        r_ = None
        if self.channel is None:
            return
        if self.player == subj:
            if self.player_ready:
                self.player_ready = r_ = False
            else:
                self.player_ready = r_ = True
        elif self.opponent == subj:
            if self.opponent_ready:
                self.opponent_ready = r_ = False
            else:
                self.opponent_ready = r_ = True
        else:
            return
        if r_:
            self.scrim.write_log(f"[{get_nowtime_str()}] {self}: {subj.name} readyed.\n")
            await self.channel.send(embed=discord.Embed(
                title=f"{subj.name} ready!",
                color=discord.Colour.green()
            ))
        else:
            self.scrim.write_log(f"[{get_nowtime_str()}] {self}: {subj.name} unreadyed.\n")
            await self.channel.send(embed=discord.Embed(
                title=f"{subj.name} unready!",
                color=discord.Colour.green()
            ))

    def is_all_ready(self):
        return self.player_ready and self.opponent_ready

    def reset_ready(self):
        self.player_ready = False
        self.opponent_ready = False
        self.scrim.write_log(f"[{get_nowtime_str()}] {self}: Ready status reset.\n")

    async def go_next_status(self, timer_cancelled):
        self.readyable = False
        if self.round == -1:
            if timer_cancelled:
                await self.channel.send(embed=discord.Embed(
                    title="ALL READY!",
                    description="Making match & Selecting mappool...",
                    color=discord.Colour.dark_red()
                ))

                await self.scrim.maketeam("RED", False)
                await self.scrim.maketeam("BLUE", False)
                await self.scrim.addplayer("RED", self.player, False)
                await self.scrim.addplayer("BLUE", self.opponent, False)
                self.scrim.setmoderule(
                    {0, 128, },  # NM
                    {16, 144, },  # HD
                    {8, 136, },  # HR
                    {32, 160, },  # DT
                    {0, 1, 8, 16, 17, 24, 128, 129, 136, 144, 145, 152},  # FM
                    {0, 1, 8, 16, 17, 24, 128, 129, 136, 144, 145, 152}  # TB
                )
            else:
                await self.channel.send(embed=discord.Embed(
                    title="The Opponent didn't participate.",
                    description="Match aborted.",
                    color=discord.Colour.dark_red()
                ))
                self.aborted = True
        elif self.round == 0:
            if timer_cancelled:
                await self.channel.send(embed=discord.Embed(
                    title="ALL READY!",
                    description="Preparing the round...",
                    color=discord.Colour.dark_red()
                ))
            else:
                await self.channel.send(embed=discord.Embed(
                    title="The Opponent didn't ready.",
                    description="Match aborted.",
                    color=discord.Colour.dark_red()
                ))
                self.aborted = True
        else:
            if timer_cancelled:
                message = await self.channel.send(embed=discord.Embed(
                    title="ALL READY!",
                    description=f"Round #{self.round} starts in 10...",
                    color=discord.Colour.purple()
                ))
                for i in range(9, -1, -1):
                    await asyncio.gather(message.edit(embed=discord.Embed(
                        title="ALL READY!",
                        description=f"Round #{self.round} starts in **{i}**...",
                        color=discord.Colour.purple()
                    )), asyncio.sleep(1))
            else:
                message = await self.channel.send(embed=discord.Embed(
                    title="READY TIME OVER!",
                    description=f"Force Round #{self.round} to start in 10...",
                    color=discord.Colour.purple()
                ))
                for i in range(9, -1, -1):
                    await asyncio.gather(message.edit(embed=discord.Embed(
                        title="READY TIME OVER!",
                        description=f"**Force** Round #{self.round} to start in **{i}**...",
                        color=discord.Colour.purple()
                    )), asyncio.sleep(1))
            await self.scrim.do_match_start()
            mid = self.scrim.getmapid()[0]
            self.playID = {self.player.id: await self.bot.req.create_playID(self.uuid[self.player.id], mid),
                           self.opponent.id: await self.bot.req.create_playID(self.uuid[self.opponent.id], mid)}
            if isinstance(pl := self.playID[self.player.id], self.bot.req.ERRORS):
                self.scrim.write_log(self.bot.req.censor(str(pl.data)) + '\n')
                raise pl
            if isinstance(op := self.playID[self.opponent.id], self.bot.req.ERRORS):
                self.scrim.write_log(self.bot.req.censor(str(op.data)) + '\n')
                raise op
            if (mh := pl['mapHash']) == op['mapHash']:
                self.scrim.setmaphash(mh)
            if not timer_cancelled:
                self.player_ready = True
                self.opponent_ready = True
        self.round += 1

    async def do_progress(self):
        name = self.match_id if self.match_id else self.__id
        if self.match_end or self.aborted:
            return
        elif self.round == -1:
            chname = f"match-{name}"
            guild = self.bot.RANKED_OSUDROID_GUILD
            self.role = await guild.create_role(name=chname, color=discord.Colour.random())
            await self.player.add_roles(self.role)
            await self.opponent.add_roles(self.role)
            if guild.id == RANKED_OSUDROID_GUILD_ID:
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(read_messages=False),
                    guild.get_role(823415179177885706):
                        discord.PermissionOverwrite(read_messages=True, send_messages=False),  # verified
                    guild.get_role(823730690058354688):
                        discord.PermissionOverwrite(read_messages=True, send_messages=True),  # Staff member
                    self.role: discord.PermissionOverwrite(read_messages=True, send_messages=True)
                }
            else:
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(read_messages=True, send_messages=False),
                    self.role: discord.PermissionOverwrite(read_messages=True, send_messages=True)
                }
            self.channel = await self.bot.match_place.create_text_channel(chname, overwrites=overwrites)
            self.player_info = await self.bot.get_user_info(self.player.id)
            if isinstance(self.player_info, self.bot.req.ERRORS):
                await self.channel.send(embed=discord.Embed(
                        title="Error occurred!",
                        description=f"`{self.player_info}`\nCheck the log."
                ))
                self.scrim.write_log(self.bot.req.censor(str(self.player_info.data)) + '\n')
                raise self.player_info
            self.opponent_info = await self.bot.get_user_info(self.opponent.id)
            if isinstance(self.opponent_info, self.bot.req.ERRORS):
                await self.channel.send(
                    embed=discord.Embed(
                        title="Error occurred!",
                        description=f"`{self.opponent_info}`\nCheck the log."
                    )
                )
                self.scrim.write_log(self.bot.req.censor(str(self.opponent_info.data)) + '\n')
                raise self.opponent_info
            self.uuid[self.player.id] = self.player_info['uuid']
            self.uuid[self.opponent.id] = self.opponent_info['uuid']
            # rate_lower, rate_highter = sorted(self.elo_manager.get_ratings())
            if self.duel_mappool_targ is not None:
                if isinstance(self.duel_mappool_targ, int):
                    self.duel_mappool_targ = min(
                        filter(
                            lambda x: x['uuid'] not in unplayable_pools_uuid, 
                            maidbot_pools.values()
                        ),
                        key=lambda x: abs(x['averageMMR'] - self.duel_mappool_targ)
                    )['uuid']
                elif isinstance(self.duel_mappool_targ, str):
                    if maidbot_pools.get(self.duel_mappool_targ) is None:
                        await self.channel.send(embed=discord.Embed(
                            title="Wrong UUID!",
                            description=f"Mappool of uuid {self.duel_mappool_targ} not existing! "
                                        f"Choosing random mappool...",
                            color=discord.Colour(0x0ef37c)
                        ))
                        self.duel_mappool_targ = None
                else:
                    raise ValueError(f"Wrong type of duel-specified-mappool data: "
                                     f"{type(self.duel_mappool_targ).__name__!r}")
            res = await self.bot.req.create_match(*self.uuid.values(), self.duel_mappool_targ)
            if isinstance(res, self.bot.req.ERRORS):
                self.scrim.write_log(self.bot.req.censor(str(res.data)) + '\n')
                raise res
            self.match_id = res["matchId"]
            tempname = f"match-{self.match_id}"
            await self.role.edit(name=tempname)
            await self.channel.edit(name=tempname)
            self.mappool_uuid = res['mappool']
            self.mappool_info = maidbot_pools.get(self.mappool_uuid)
            # self.scrim.write_log('Before select_pool_mmr_range :', rate_lower, rate_highter)
            # 1000 ~ 2000 => 1200 ~ 3300
            # rate_lower = elo_convert(rate_lower)
            # rate_highter = elo_convert(rate_highter)
            # self.scrim.write_log('After  select_pool_mmr_range :', rate_lower, rate_highter)
            #
            #    pool_pools = list(filter(
            #        lambda po:
            #        min(rate_lower, SELECT_POOL_HIGHEST) - SELECT_POOL_RANGE
            #        <= po['averageMMR']
            #        <= max(rate_highter, SELECT_POOL_LOWEST) + SELECT_POOL_RANGE,
            #        maidbot_pools.values()
            #    ))
            #    selected_pool = random.choice(pool_pools)
            #    while selected_pool['uuid'] in unplayable_pools_uuid:
            #        selected_pool = random.choice(pool_pools)
            # assert selected_pool is not None
            # self.mappool_uuid = selected_pool['uuid']
            # self.scrim.write_log('Selected pool :', selected_pool['name'])
            self.scrim = Scrim(self.bot, self.channel, self)
            self.elo_manager.set_player_rating(ftod(self.player_info['elo']))
            self.elo_manager.set_opponent_rating(ftod(self.opponent_info['elo']))
            await self.channel.send(
                f"{self.player.mention} {self.opponent.mention}",
                embed=discord.Embed(
                    title="Match initiated!",
                    description="Chat `rdy` to participate in 2 minutes!"
                )
            )
            self.timer = Timer(self.bot, self.channel, f"Match_{name}_invite", 120, self.go_next_status)
            self.scrim.write_log(f"[{get_nowtime_str()}] {self}: Match initiated\n"
                                 f"Player   ID : {self.player.id}\n"
                                 f"              {self.uuid[self.player.id]}\n"
                                 f"Opponent ID : {self.opponent.id}\n"
                                 f"              {self.uuid[self.opponent.id]}\n"
                                 f"Channel  ID : {self.channel.id}\n"
                                 f"Role     ID : {self.role.id}\n")
        elif self.round == 0:
            await self.channel.send(embed=discord.Embed(
                title="Mappool is...",
                description=f"Mappool Name : `{self.mappool_info['name']}`\n"
                            f"Mappool MMR (not modified) : "
                            f"{self.mappool_info['averageMMR']}\n"
                            f"Mappool UUID : `{self.mappool_uuid}`",
                color=discord.Colour(0x0ef37c)
            ))
            self.scrim.write_log(f"[{get_nowtime_str()}] {self}.do_progress(): Mappool info\n"
                                 f"Pool name : {self.mappool_info['name']}\n"
                                 f"Pool UUID : {self.mappool_uuid}\n")

            calcmsg = await self.channel.send(embed=discord.Embed(
                title="Mappool initiating...",
                color=discord.Colour.blurple()
            ))

            maps = await self.bot.req.get_mappool(self.mappool_uuid)
            for md in maps:
                tempmap = await self.bot.osuapi.get_beatmaps(beatmap_id=md['mapId'])
                if len(tempmap) == 0:
                    self.scrim.write_log(f"[{get_nowtime_str()}] {self}.do_progress(): "
                                         f"UNPLAYABLE MAP FOUND - {md['mapId']}\n")
                    await calcmsg.edit(content=f"{self.player.mention} {self.opponent.mention}", embed=discord.Embed(
                        title="There's unplayable map in the mappool!",
                        description=f"Map id = {md['mapId']}\n"
                                    f"Call the moderator.\n"
                                    f"**This match will be aborted.**"
                    ))
                    self.aborted = True
                    continue
                self.map_infos[fixca.FixcaMapMode(md['mods']).name + str(md['sheetId'])] = tempmap[0]
            if self.aborted:
                return

            maps = dict([(i, []) for i in modes])
            for k in self.map_infos:
                m = moder.match(k)
                if m:
                    maps[m.group(1)].append(k)
            for mm in maps:
                random.shuffle(maps[mm])
            mode_order = ['NM', 'HD', 'HR', 'DT']
            random.shuffle(mode_order)
            for mm in mode_order:
                self.map_order.append(maps[mm].pop())
            self.map_order.append(maps['FM'].pop())
            self.map_order.append(maps['NM'].pop())
            self.map_tb = maps['TB'].pop()

            await calcmsg.edit(content=f"{self.player.mention} {self.opponent.mention}", embed=discord.Embed(
                title="Mappool successfully initiated!",
                description=f"If you got ready, chat `rdy`.\n"
                            f"You have 1 minute to continue.",
                color=discord.Colour.blue()
            ))
            self.timer = Timer(self.bot, self.channel, f"Match_{name}_finalready", 60, self.go_next_status)
            self.scrim.write_log(f"[{get_nowtime_str()}] {self}.do_progress(): Mappool successfully initiated.\n")
        elif (self.map_tb is None and self.round > len(self.map_order)) or self.round > self.BO or \
                self.winfor in set(self.scrim.setscore.values()):
            await self.scrim.end()
            score_diff = \
                self.scrim.setscore["RED"] - self.scrim.setscore["BLUE"]
            div_ = d(2 * self.winfor)
            rate = d('.5') + score_diff / div_
            prate_bef, orate_bef = self.elo_manager.get_ratings()
            pdrate, odrate = self.elo_manager.update(rate, True)
            prate_aft, orate_aft = self.elo_manager.get_ratings()
            if self.is_duel:
                await self.channel.send(embed=discord.Embed(
                    title="MATCH FINISHED",
                    color=discord.Colour(0xcaf32a)
                ))
            else:
                await self.channel.send(embed=discord.Embed(
                    title="MATCH FINISHED",
                    description=f"__{self.player.display_name}__ : "
                                f"{elo_show_form(prate_bef)} => **{elo_show_form(prate_aft)}** "
                                f"({pdrate:+.3f})\n"
                                f"__{self.opponent.display_name}__ : "
                                f"{elo_show_form(orate_bef)} => **{elo_show_form(orate_aft)}** "
                                f"({odrate:+.3f})\n",
                    color=discord.Colour(0xcaf32a)
                ))
            self.match_end = True
            namelen = max(len(self.player.name), len(self.opponent.name))
            temptxt = f"[{get_nowtime_str()}] {self}.do_progress(): Match finished.\n" \
                      f"{self.player.name:{namelen}s} Before ELO : {prate_bef}\n" \
                      f"{self.player.name:{namelen}s} After  ELO : {prate_aft}\n" \
                      f"{self.opponent.name:{namelen}s} Before ELO : {orate_bef}\n" \
                      f"{self.opponent.name:{namelen}s} After  ELO : {orate_aft}\n"
            with open(self.scrim.log.name, 'a', encoding='utf-8') as f:
                f.write(temptxt)
        else:
            if self.round == self.BO and self.map_tb is not None:
                now_mapnum = self.map_tb
            else:
                now_mapnum = self.map_order[self.round - 1]
            now_beatmap = self.map_infos[now_mapnum]
            self.scrim.setnumber(now_mapnum)
            self.scrim.setartist(now_beatmap.artist)
            self.scrim.setauthor(now_beatmap.creator)
            self.scrim.settitle(now_beatmap.title)
            self.scrim.setdiff(now_beatmap.version)
            self.scrim.setmaplength(now_beatmap.total_length)
            self.scrim.setmode(now_mapnum[:2])
            self.scrim.setmapid(now_beatmap.beatmap_id, now_beatmap.beatmapset_id)
            mid = self.scrim.getmapid()
            download_link = f"Osu!\t: https://osu.ppy.sh/beatmapsets/{mid[1]}#osu/{mid[0]}\n" \
                            f"Chimu\t: https://chimu.moe/en/d/{mid[1]}\n" \
                            f"Beatconnect\t: https://beatconnect.io/b/{mid[1]}"
            await self.channel.send(embed=discord.Embed(
                title=f"Round #{self.round} Map selected!",
                description=f"Map Info : `{self.scrim.getmapfull()}`\n"
                            f"Map Number : `{self.scrim.getnumber()}`\n"
                            f"Map Length : `{self.scrim.getmaplength()}` sec\n"
                            f"Allowed modes : "
                            f"`{', '.join(map(inttomode, self.scrim.availablemode[self.scrim.getmode()]))}`\n\n"
                            f"*Download links here :*\n{download_link}",
                color=discord.Colour.blue()
            ))
            await self.channel.send(embed=discord.Embed(
                title=f"IMPORTANTS :",
                description=f"Difficulty : **{self.scrim.getdiff()}**\n"
                            f"Allowed modes : "
                            f"`{', '.join(map(inttomode, self.scrim.availablemode[self.scrim.getmode()]))}`",
                color=discord.Colour.green()
            ))
            await self.channel.send(embed=discord.Embed(
                title=f"Round #{self.round} ready!",
                description="Chat `rdy` in 5 minutes.",
                color=discord.Colour.orange()
            ))
            self.timer = Timer(self.bot, self.channel, f"Match_{name}_{self.round}", 300, self.go_next_status)
            self.scrim.write_log(f"[{get_nowtime_str()}] {self}.do_progress(): Round #{self.round} prepared.\n"
                                 f"Map info : {self.scrim.getmapfull()}\n"
                                 f"Map ID   : {self.scrim.getmapid()}\n"
                                 f"Map mode : {self.scrim.getnumber()}\n")

    async def match_start(self):
        try:
            while not self.match_end or self.aborted:
                if self.scrim is not None:
                    self.scrim.write_log(f"[{get_nowtime_str()}] {self}.match_task: Round #{self.round} processing.\n")
                await self.do_progress()
                self.readyable = True
                while True:
                    if self.match_end:
                        self.scrim.write_log(
                            f"[{get_nowtime_str()}] {self}.match_task: Round #{self.round} match_end detected.\n")
                        await self.channel.send(embed=discord.Embed(
                            title="Match successfully finished",
                            description="Delete after 180 seconds."
                        ))
                        break
                    elif self.aborted:
                        self.scrim.write_log(
                            f"[{get_nowtime_str()}] {self}.match_task: Round #{self.round} aborted detected.\n")
                        await self.channel.send(embed=discord.Embed(
                            title="Match successfully aborted",
                            description="Delete after 15 seconds."
                        ))
                        break
                    if self.is_all_ready():
                        self.scrim.write_log(
                            f"[{get_nowtime_str()}] {self}.match_task: Round #{self.round} all_ready detected.")
                        await self.timer.cancel()
                        self.reset_ready()
                        # if self.scrim is not None and not self.scrim.match_task.done():
                        if self.round > 1 and not (self.match_end or self.aborted):
                            await self.scrim.match_task
                            for playid in self.playID.values():
                                await self.bot.req.expire_playid(playid['playId'])
                        break
                    await asyncio.sleep(1)
                if self.match_end:
                    if not self.is_duel:
                        await self.bot.req.upload_elo(self)
                    break
                if self.aborted:
                    break
        except asyncio.CancelledError:
            raise
        except BaseException as ex_:
            await self.channel.send(embed=discord.Embed(
                title="Error occurred!",
                description=f"`{ex_}`\nCheck the log.\n**This match will be aborted.**",
            ))
            if self.scrim is None:
                stream = print
            else:
                stream = self.scrim.write_log
            stream(f'[{get_nowtime_str()}] {self}.match_task (Round #{self.round}):\n')
            stream(get_traceback_str(ex_) + '\n')
            self.aborted = True
        finally:
            if self.match_id != 'None':
                res = await self.bot.req.end_match(self.match_id, self.aborted)
                if isinstance(res, self.bot.req.ERRORS):
                    self.scrim.write_log(self.bot.req.censor(str(res.data)) + '\n')
            if self.scrim is not None:
                if not self.scrim.log.closed:
                    self.scrim.log.close()
                if self.scrim.match_task is not None and not self.scrim.match_task.done():
                    self.scrim.match_task.cancel()
            self.bot.finished_matches.append(self)
            del self.bot.matches[self.player], self.bot.matches[self.opponent]

            async def do_stuff(*args):
                if not self.match_task.done():
                    self.match_task.cancel()
                await self.channel.delete()
                await self.role.delete()
                # self.bot.finished_matches.remove(self)

            self.timer = Timer(
                self.bot,
                self.channel,
                f"Match_{self.get_id()}_delete",
                15 if self.aborted else 180,
                do_stuff
            )

    async def do_match_start(self):
        if self.match_task is None or self.match_task.done():
            self.match_task = self.bot.loop.create_task(self.match_start())
        else:
            await self.channel.send(embed=discord.Embed(
                title="Match is already processing!",
                description="Try again after the match ends.",
                color=discord.Colour.dark_red()
            ))

    async def surrender(self, ctx):
        if self.round < 0:
            return
        player = ctx.author
        tn = None
        if player == self.player:
            tn = "BLUE"
        elif player == self.opponent:
            tn = "RED"
        else:
            return

        def check(msg):
            return msg.author == player and msg.content == player.name

        await ctx.send(
            f"**{player.mention}, if yor really want to surrender, send your name (`{player.name}`) in 30 seconds.**")
        try:
            await self.bot.wait_for('message', timeout=30, check=check)
        except asyncio.TimeoutError:
            await ctx.send(f"**{player.mention}, time over.**")
            return
        await self.channel.send(embed=discord.Embed(
            title=f"{player.name} surrendered",
            description="The match will finish soon..."
        ))
        self.scrim.setscore[tn] = int(self.winfor)
        if self.scrim.match_task is not None and not self.scrim.match_task.done():
            self.scrim.match_task.cancel()
        if not self.timer.done:
            await self.timer.cancel(False)
        self.round = self.BO + 1
        await self.do_progress()

