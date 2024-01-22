import asyncio

from app.event import pipeline_pass


async def main():
    with open(file="../risk.jpg", mode="rb") as f:
        s = await pipeline_pass(trace_id="test", content=f)
        print(s)


# anime_score=0.01 risk_tag=['loli', '6+girls', 'multiple_girls', 'censored'] anime_tags=['breasts', 'multiple_girls', 'medium_breasts', 'underwear', 'nipples', 'panties', 'ass', 'hetero', 'censored', 'multiple_boys', 'penis', 'pussy', 'sex', 'clothes_lift', 'loli', 'anus', 'bottomless', '6+girls', 'shirt_lift', 'panty_pull', '6+boys', 'chart']


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
