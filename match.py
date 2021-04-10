from friend_import import *
from scrim import Scrim
from timer import Timer
from mappoolmaker import MappoolMaker
from elo_rating import EloRating

if TYPE_CHECKING:
    from friend import MyBot

class Match_Scrim:
    def __init__(self,
                 bot: 'MyBot',
                 player: discord.Member,
                 opponent: discord.Member,
                 bo: int = 7):
        self.bot = bot
        self.loop = bot.loop
        self.made_time = datetime.datetime.utcnow().strftime("%y%m%d%H%M%S%f")
        self.channel: Optional[discord.TextChannel] = None
        self.player = player
        self.opponent = opponent

        self.mappoolmaker: Optional[MappoolMaker] = None
        self.map_order: List[str] = []
        self.map_autoscores: Dict[str, int] = dict()
        self.map_hashes: Dict[str, str] = dict()
        self.map_tb: Optional[str] = None

        self.scrim: Optional[Scrim] = None
        self.timer: Optional[Timer] = None
        self.diff_form: str = '[number] artist - title [diff]'

        self.round = -1
        # -2 = 매치 생성 전
        # -1 = 플레이어 참가 대기
        # 0 = 맵풀 다운로드 대기
        # n = n라운드 준비 대기
        self.bo = bo
        self.winfor = (bo / d('2')).to_integral(rounding=decimal.ROUND_HALF_UP)
        self.abort = False

        self.player_ELO = self.bot.ratings[self.bot.uids[self.player.id]]
        self.opponent_ELO = self.bot.ratings[self.bot.uids[self.opponent.id]]
        self.elo_manager = EloRating(self.player_ELO, self.opponent_ELO, ELO_K, ELO_STDV)

        self.player_ready: bool = False
        self.opponent_ready: bool = False

        self.match_task: Optional[asyncio.Task] = None

    def get_debug_txt(self):
        if self.match_task.exception() is not None:
            return get_traceback_str(self.match_task.exception())

    async def switch_ready(self, subj):
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
            await self.channel.send(embed=discord.Embed(
                title=f"{subj} ready!",
                color=discord.Colour.green()
            ))
        else:
            await self.channel.send(embed=discord.Embed(
                title=f"{subj} unready!",
                color=discord.Colour.green()
            ))

    def is_all_ready(self):
        return self.player_ready and self.opponent_ready

    def reset_ready(self):
        self.player_ready = False
        self.opponent_ready = False

    async def go_next_status(self, timer_cancelled):
        if self.round == -1:
            if timer_cancelled:
                self.round = 0
                await self.channel.send(embed=discord.Embed(
                    title="ALL READY!",
                    description="Making match & mappool...",
                    color=discord.Colour.dark_red()
                ))

                await self.scrim.maketeam(self.player.name, False)
                await self.scrim.maketeam(self.opponent.name, False)
                await self.scrim.addplayer(self.player.name, self.player, False)
                await self.scrim.addplayer(self.opponent.name, self.opponent, False)
                self.scrim.setmoderule(
                    {8, },
                    {9, },
                    {10, },
                    {12, 13},
                    {9, 10, 11, 72, 73},
                    {8, 9, 10, 11, 72, 73}
                )
            else:
                await self.channel.send(embed=discord.Embed(
                    title="The Opponent didn't participate.",
                    description="Match aborted.",
                    color=discord.Colour.dark_red()
                ))
                self.abort = True
        elif self.round == 0:
            if timer_cancelled:
                self.round = 1
                await self.channel.send(embed=discord.Embed(
                    title="ALL READY!",
                    description="Preparing the round...",
                    color=discord.Colour.dark_red()
                ))
                await self.scrim.setform(self.diff_form)
                # send POST match init
            else:
                await self.channel.send(embed=discord.Embed(
                    title="The Opponent didn't ready.",
                    description="Match aborted.",
                    color=discord.Colour.dark_red()
                ))
                self.abort = True
        else:
            if timer_cancelled:
                message = await self.channel.send(embed=discord.Embed(
                    title="ALL READY!",
                    description=f"Round #{self.round} starts in 10...",
                    color=discord.Colour.purple()
                ))
                for i in range(9, -1, -1):
                    await message.edit(embed=discord.Embed(
                        title="ALL READY!",
                        description=f"Round #{self.round} starts in **{i}**...",
                        color=discord.Colour.purple()
                    ))
                    await asyncio.sleep(1)
            else:
                message = await self.channel.send(embed=discord.Embed(
                    title="READY TIME OVER!",
                    description=f"Force Round #{self.round} to start in 10...",
                    color=discord.Colour.purple()
                ))
                for i in range(9, -1, -1):
                    await message.edit(embed=discord.Embed(
                        title="READY TIME OVER!",
                        description=f"**Force** Round #{self.round} to start in **{i}**...",
                        color=discord.Colour.purple()
                    ))
                    await asyncio.sleep(1)
            self.round += 1
            await self.scrim.do_match_start()

    async def do_progress(self):
        if self.abort:
            return
        elif self.round == -1:
            self.channel = await self.bot.match_category_channel.create_text_channel(f"Match_{self.made_time}")
            self.scrim = Scrim(self.bot, self.channel)
            await self.channel.send(
                f"{self.player.mention} {self.opponent.mention}",
                embed=discord.Embed(
                    title="Match initiated!",
                    description="Chat `rdy` to participate in 2 minutes!"
                )
            )
            self.timer = Timer(self.bot, self.channel, f"Match_{self.made_time}_invite", 120, self.go_next_status)
        elif self.round == 0:
            rate_lower, rate_highter = sorted(self.elo_manager.get_ratings())
            print('Before select_pool_mmr_range :', rate_lower, rate_highter)
            # 1000 ~ 2000 => 1200 ~ 3300
            rate_lower = elo_convert(rate_lower)
            rate_highter = elo_convert(rate_highter)
            print('After  select_pool_mmr_range :', rate_lower, rate_highter)
            pool_pools = list(filter(
                lambda po: rate_lower - 50 <= po <= rate_highter + 50,
                maidbot_pools
            ))
            selected_pool = random.choice(pool_pools)
            print('Selected pool :', selected_pool['name'])
            await self.channel.send(embed=discord.Embed(
                title="Mappool is selected!",
                description=f"Mappool Name : `{selected_pool['name']}`\n"
                            f"Mappool MMR (modified) : {elo_convert_rev(selected_pool['averageMMR'])}\n"
                            f"Mappool UUID : `{selected_pool['uuid']}`",
                color=discord.Colour(0x0ef37c)
            ))

            statusmessage = await self.channel.send(embed=discord.Embed(
                title="This message is for showing mappool making process.",
                description="If you see this message for more than 5 seconds, call the bot developer.",
                color=discord.Colour.orange()
            ))
            self.mappoolmaker = MappoolMaker(self, statusmessage, self.made_time)

            # 테스트 데이터 : 디코8토너 쿼터파이널
            # self.mappoolmaker.maps = {
            #     'NM1': (714329, 1509639), 'NM2': (755844, 1590814), 'NM3': (145215, 424925), 'NM4': (671199, 1419243),
            #     'HR1': (41874, 132043), 'HR2': (136065, 363010), 'HR3': (90385, 245284),
            #     'HD1': (708305, 1497483), 'HD2': (931886, 1945754), 'HD3': (739053, 1559618),
            #     'DT1': (223092, 521280), 'DT2': (26226, 88633), 'DT3': (190754, 454158),
            #     'FM1': (302535, 678106), 'FM2': (870225, 1818604), 'FM3': (830444, 1768797),
            #     'TB': (1009680, 2248906)
            # }

            mappool_link = await self.mappoolmaker.execute_osz_from_fixca(selected_pool['uuid'])
            if mappool_link[0] is False:
                print(mappool_link[1])
                await self.channel.send(embed=discord.Embed(
                    title="Error occurred",
                    description=mappool_link[1] + '\nRetry soon by downloading each beatmaps...'
                ))
                for bm in selected_pool['maps']:
                    self.mappoolmaker.add_map(bm['sheetId'], bm['mapSetId'], bm['mapId'])
                mappool_link = await self.mappoolmaker.execute_osz()
                if mappool_link[0] is False:
                    print(mappool_link[1])
                    await self.channel.send(embed=discord.Embed(
                        title="Error occurred",
                        description=mappool_link[1]
                    ))
                    return
            else:
                self.diff_form = '[number] artist - title(diff)'
            mappool_link = mappool_link[1]

            maps = dict([(i, []) for i in modes])
            for k in self.mappoolmaker.beatmap_objects.keys():
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

            await self.channel.send(f"{self.player.mention} {self.opponent.mention}", embed=discord.Embed(
                title="Mappool is made!",
                description=f"Please download from here : {mappool_link}\n"
                            f"If any error occured during the process, "
                            f"abort this match and call the bot developer.\n"
                            f"If you finished downloading and got ready, chat `rdy`.\n"
                            f"You have 5 minutes to download the mappool.",
                color=discord.Colour.blue()
            ))
            self.timer = Timer(self.bot, self.channel, f"Match_{self.made_time}_download", 300, self.go_next_status)
        elif self.round == len(self.map_order) or self.round > self.bo or \
                self.winfor in set(self.scrim.setscore.values()):
            winner = await self.scrim.end()
            score_diff = \
                self.scrim.setscore[self.player.name] - self.scrim.setscore[self.opponent.name]
            if score_diff > 0:
                rate = d('1') - score_diff / d('16')
            elif score_diff < 0:
                rate = score_diff / d('16')
            else:
                rate = d('.5')
            self.elo_manager.update(rate, True)
            self.bot.ratings[self.bot.uids[self.player.id]], self.bot.ratings[self.bot.uids[self.opponent.id]] = \
                self.elo_manager.get_ratings()
            shutil.rmtree(self.mappoolmaker.save_folder_path)
            self.abort = True
        else:
            if self.round == self.bo and self.map_tb is not None:
                now_mapnum = self.map_tb
            else:
                now_mapnum = self.map_order[self.round - 1]
            maphash = self.map_hashes.get(now_mapnum)
            if maphash is None:
                maphash = self.mappoolmaker.get_map_hash(now_mapnum)
            if not isinstance(maphash, Exception):
                self.scrim.setmaphash(maphash)
            now_beatmap: osuapi.osu.Beatmap = self.mappoolmaker.beatmap_objects[now_mapnum]
            self.scrim.setnumber(now_mapnum)
            self.scrim.setartist(now_beatmap.artist)
            self.scrim.setauthor(now_beatmap.creator)
            self.scrim.settitle(now_beatmap.title)
            self.scrim.setdiff(now_beatmap.version)
            self.scrim.setmaptime(now_beatmap.total_length)
            self.scrim.setmode(now_mapnum[:2])
            autosc = self.map_autoscores.get(now_mapnum)
            if autosc is None:
                scorecalc = scoreCalc.scoreCalc(os.path.join(
                    self.mappoolmaker.save_folder_path, self.mappoolmaker.osufile_path[now_mapnum]))
                autosc = scorecalc.getAutoScore()[1] // 2
                scorecalc.close()
            self.scrim.setautoscore(autosc)
            await self.channel.send(embed=discord.Embed(
                title=f"Map infos Modified!",
                description=f"Map Info : `{self.scrim.getmapfull()}`\n"
                            f"Map Number : {self.scrim.getnumber()} / Map Mode : {self.scrim.getmode()}\n"
                            f"Map SS Score : {self.scrim.getautoscore()} / Map Length : {self.scrim.getmaptime()} sec\n"
                            f"Map Hash : {self.scrim.getmaphash()}\n"
                            f"Allowed modes : "
                            f"`{', '.join(map(inttomode, self.scrim.availablemode[self.scrim.getmode()]))}`",
                color=discord.Colour.blue()
            ))
            await self.channel.send(embed=discord.Embed(
                title=f"Round #{self.round} ready!",
                description="Chat `rdy` in 2 minutes.",
                color=discord.Colour.orange()
            ))
            self.timer = Timer(self.bot, self.channel, f"Match_{self.made_time}_{self.round}", 120, self.go_next_status)

    async def match_start(self):
        try:
            while not self.abort:
                await self.do_progress()
                while True:
                    if self.abort:
                        await self.channel.send(embed=discord.Embed(
                            title="Match successfully finished"
                        ))
                        break
                    if self.is_all_ready():
                        await self.timer.cancel()
                        self.reset_ready()
                        # if self.scrim is not None and not self.scrim.match_task.done():
                        if self.round > 1:
                            await self.scrim.match_task
                            r = self.scrim.match_task.result()
                            data = {
                                'key': fixca_key,
                                'matchId': self.made_time,
                                'mapId': self.mappoolmaker.maps[r['number']][0],
                                'mapSetId': self.mappoolmaker.maps[r['number']][1],
                                'mapName': r['map'],
                                'mapMod': r['mode'],
                                'mapSheet': r['number'],
                                'playerScore': r['v2score'][self.player.id],
                                'opponentScore': r['v2score'][self.opponent.id],
                                'playerAcc': float(r['score'][self.player.id][0][1]),
                                'opponentAcc': float(r['score'][self.opponent.id][0][1]),
                                'playerMod': r['score'][self.player.id][2],
                                'opponentMod': r['score'][self.opponent.id][2],
                                'startedTime': r['start_time']
                            }
                            if BOT_DEBUG:
                                async with self.bot.session.post("http://ranked-osudroid.kro.kr/roundSubmit",
                                                                 data=data) as submit_res:
                                    if submit_res.status != 200:
                                        await self.channel.send(embed=discord.Embed(
                                            title=f'POST failed. ({submit_res.status})\n',
                                            description=f'Try again.',
                                            color=discord.Colour.dark_red()
                                        ))
                                    if (submit_res_json := await submit_res.json(encoding='utf-8'))['status'] == 'failed':
                                        await self.channel.send(embed=discord.Embed(
                                            title=f'POST failed. (FIXCUCKED)\n',
                                            description=f'```{submit_res_json["error"]}```\n\nTry again.',
                                            color=discord.Colour.dark_red()
                                        ))
                        break
                    await asyncio.sleep(1)
                if self.abort:
                    break
        except BaseException as ex_:
            print(get_traceback_str(ex_))
            raise ex_
        finally:
            if self.mappoolmaker.drive_file is not None:
                self.mappoolmaker.drive_file.Delete()
            del self.bot.matches[self.player], self.bot.matches[self.opponent]

    async def do_match_start(self):
        if self.match_task is None or self.match_task.done():
            self.match_task = self.loop.create_task(self.match_start())
        else:
            await self.channel.send(embed=discord.Embed(
                title="Match is already processing!",
                description="Try again after the match ends.",
                color=discord.Colour.dark_red()
            ))
