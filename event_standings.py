import requests
import csv
import json
import re
from uuid import uuid3, NAMESPACE_DNS
from sqlalchemy import create_engine, MetaData, inspect, Column, String, Table, Uuid, Integer
from sqlalchemy.orm import Session, DeclarativeBase
from sqlalchemy.orm import DeclarativeBase
from bs4 import BeautifulSoup

ENGINE = create_engine("postgresql://emry:271061@localhost/fabtcg_events")

class Base(DeclarativeBase):
    metadata = MetaData()
            
class Player(Base):
    __table__ = Table("player", Base.metadata, Column("player_event_id", String, primary_key=True), autoload_with=ENGINE)

class FabEvent(Base):
    __table__ = Table("fabtcg_event", Base.metadata, Column("url", String, primary_key=True), autoload_with=ENGINE)

def populate_events() -> list:
    with open("silver_age_events.csv", newline="") as file:
        event_reader = csv.reader(file, delimiter=",",)
        next(event_reader)

        return [
            FabEvent(
                url=record[0],
                event_date=record[1],
                tier=int(record[2])
            )
            for record in event_reader
        ]

def get_event_standing_pages(event: FabEvent) -> dict:
    FABTCG_URL = "https://fabtcg.com/coverage/{}/standings/{}" #{event_url}/standings/{round number}
    HEADER = {"From":"emry.kinney@gmail.com","User-Agent":"Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36 Vivaldi/8.2.4133.76"}
    
    output = list()

    rounds = range(1,30) #End of range unrealisticaly high to catch if events go more rounds of swiss than typical

    standings_url = [FABTCG_URL.format(event.url, round) for round in rounds]

    print(f"Getting Round 1 Standings for {event.url}")
    for idx, url in enumerate(standings_url):
        
        response = requests.get(url, headers=HEADER)

        if response.status_code == 200:
            soup = BeautifulSoup(response.text,  "html")

            if not soup.find("div", {"class":"text-center py-10"}):
                output.append(response.text)
                print(f"Getting Round {idx + 2}")
            else:
                event.swiss_rounds = idx
                print(f"{event.url} Swiss Rounds over at Round {idx}")
                break
        else:
            print(f"{response.status_code} - {standings_url}")
    
    #Throw away swiss once event.swiss_rounds is updated
    return output

def build_event_players(event_url: str, standings_pages: list) -> dict:
    def get_player_name(tr):
        return tr.find("span",{"class":"player-name"}).text

    def get_hero_name(tr):
        if tr.find("span", {"class":"hero-name"}):
            return tr.find("span", {"class":"hero-name"}).text
        else:
            return "Undeclared"

    def get_round_standing(tr):
        if tr.find("td", {"class":"rank"}).text.isnumeric():
            return int(tr.find("td", {"class":"rank"}).text)
        else:
            return -1

    def make_player_id(name, hero, event):
        return uuid3(NAMESPACE_DNS, f"{name}{hero}{event}")

    def instantiate():
        round_1 = BeautifulSoup(standings_pages[0], "html").find_all("tr")
        event_players = {}

        for record in round_1[1:]:
            player_name = get_player_name(record)
            hero_name = get_hero_name(record)
            round_standing = get_round_standing(record)
            player_event_id = make_player_id(player_name, hero_name, event_url)

            if round_standing > 0:
                round_standing = [0]
            else:
                round_standing = [-1]

            if not event_players.get(player_event_id):
                event_players[player_event_id] = {"player_name": player_name, "hero_name": hero_name, "round_standing": round_standing, "event": event}
            else:
                event_players[player_event_id]["hero_name"] = event_players[player_event_id]["hero_name"] or hero_name

        return event_players

    def populate_rounds() -> None:
        for round in standings_pages[1:]:
            soup = BeautifulSoup(round, "html").find_all("tr")
            for record in soup[1:]:
                player_name = get_player_name(record)
                hero_name = get_hero_name(record)
                player_event_id = make_player_id(player_name, hero_name, event_url)
                
                round_standing = get_round_standing(record)
                event_players.get(player_event_id)["round_standing"].append(round_standing)

    def convert_to_sql_record() -> list[Player]:
        return [
            Player(
                player = data["player_name"],
                hero_name = data["hero_name"],
                event_name = data["event"].url,
                round_standing = data["round_standing"],
                player_event_id = str(player_id)
            ) for player_id, data in event_players.items()
        ]

    event_players = instantiate()
    populate_rounds()

    return convert_to_sql_record()

all_events = populate_events()

for event in all_events:
    standings_pages = get_event_standing_pages(event)
    event_players = build_event_players(event.url, standings_pages)

with Session(ENGINE) as session:
    session.add_all(event_players)
    session.add_all(all_events)
    
    session.commit()


