import copy
import random
import unittest

from catalog_fixture import CATALOG, MODES, POWERS, CATALOG_SNAPSHOT
from game.room import GameRoom
from game.state import authors
from game.errors import GameError


class GameTests(unittest.TestCase):
    def room(self, mode="excuses", count=1, players=3):
        clock = [1000.0]
        game = GameRoom(
            "ABCDEF",
            "Компания",
            catalog=CATALOG_SNAPSHOT,
            clock=lambda: clock[0],
            rng=random.Random(42),
        )
        game.state.update(mode=mode, count=count, capacity=None)
        tokens = [game.join("Игрок " + str(i))["token"] for i in range(players)]
        game.start(tokens[0])
        return game, tokens, clock

    def test_all_catalogue_modes_complete_without_leaking_tokens(self):
        self.assertEqual(len(CATALOG), 16)
        self.assertEqual(sum(len(value["prompts"]) for value in CATALOG.values()), 118)
        for mode, definition in CATALOG.items():
            with self.subTest(mode=mode):
                game, tokens, clock = self.room(mode)
                row = game.current()
                if game.state["phase"] == "briefing":
                    job = row["image_jobs"]["shared"]
                    game.apply_image(
                        row["round_id"],
                        "shared",
                        job["id"],
                        image=game.image_url("shared.png"),
                    )
                    self.assertEqual(game.state["phase"], "answer")
                public = game.view(None)
                self.assertNotIn("used", public)
                self.assertTrue(
                    all(
                        "token" not in p and "power" not in p for p in public["players"]
                    )
                )
                self.assertEqual(public["round"]["answers"], [])
                if definition["kind"] in ("image", "relay"):
                    for index, token in enumerate(tokens):
                        game.generate(
                            token,
                            {
                                "round_id": row["round_id"],
                                "text": "Картинка " + str(index),
                            },
                        )
                        owner = game.player(token)["id"]
                        job = row["image_jobs"][owner]
                        self.assertTrue(
                            game.apply_image(
                                row["round_id"],
                                owner,
                                job["id"],
                                image=game.image_url(str(index) + ".png"),
                            )
                        )
                        self.assertFalse(
                            game.apply_image(
                                row["round_id"],
                                owner,
                                job["id"],
                                image=game.image_url(str(index) + ".png"),
                            )
                        )
                if definition["kind"] not in ("image",):
                    self.assertIn(game.state["phase"], ("answer", "caption"))
                    for index, token in enumerate(tokens):
                        fields = definition.get("fields", [])
                        text = (
                            "\n".join(["Реплика " + str(index)] * len(fields))
                            if fields
                            else "Ответ " + str(index)
                        )
                        game.answer(token, {"round_id": row["round_id"], "text": text})
                self.assertEqual(game.state["phase"], "vote")
                self.assertTrue(
                    all(
                        "player" not in a
                        for a in game.view(tokens[0])["round"]["answers"]
                    )
                )
                for token in tokens:
                    player = game.player(token)
                    target = next(
                        answer["id"]
                        for answer in row["answers"]
                        if player["id"] not in authors(answer)
                    )
                    game.vote(token, {"round_id": row["round_id"], "answer": target})
                self.assertEqual(game.state["phase"], "reveal")
                scores = [p["score"] for p in game.state["players"]]
                game.reveal()
                self.assertEqual(scores, [p["score"] for p in game.state["players"]])
                game.next(tokens[0], row["round_id"], force=True)
                self.assertEqual(game.state["phase"], "final")
                game.start(tokens[0])
                self.assertTrue(all(p["score"] == 0 for p in game.state["players"]))

    def test_block_shield_double_and_idempotent_scoring(self):
        game, tokens, _ = self.room(players=5)
        row = game.current()
        for player, power in zip(
            game.state["players"], ["double", "shield", "block", "block", "bonus"]
        ):
            player["power"] = power
        for index, token in enumerate(tokens):
            game.answer(
                token,
                {"round_id": row["round_id"], "text": str(index), "power": index < 2},
            )
        ids = {answer["text"]: answer["id"] for answer in row["answers"]}
        for index, token in enumerate(tokens):
            body = {
                "round_id": row["round_id"],
                "answer": ids["1" if index != 1 else "0"],
            }
            if index == 2:
                body["block"] = ids["1"]
            if index == 3:
                body["block"] = ids["0"]
            game.vote(token, body)
        answers = {a["text"]: a for a in row["answers"]}
        self.assertEqual(answers["0"]["points"], 0)
        self.assertTrue(answers["0"]["blocked"])
        self.assertEqual(answers["1"]["points"], 4)
        self.assertTrue(answers["1"]["shield"])
        scores = [p["score"] for p in game.state["players"]]
        game.reveal()
        self.assertEqual(scores, [p["score"] for p in game.state["players"]])

    def test_room_tokens_authority_and_late_players_are_isolated(self):
        first, tokens, _ = self.room()
        other, others, _ = self.room()
        with self.assertRaises(GameError) as error:
            first.player(others[0])
        self.assertEqual(error.exception.status, 401)
        with self.assertRaises(GameError) as error:
            first.lobby(tokens[1])
        self.assertEqual(error.exception.status, 403)
        late = first.join("Поздний")["token"]
        self.assertTrue(first.player(late)["waiting"])
        with self.assertRaises(GameError):
            first.answer(
                late, {"round_id": first.current()["round_id"], "text": "late"}
            )
        self.assertNotEqual(
            first.player(tokens[0])["id"], other.player(others[0])["id"]
        )

    def test_old_image_result_does_not_change_a_new_round(self):
        game, tokens, _ = self.room("clue")
        row = game.current()
        game.generate(tokens[0], {"round_id": row["round_id"], "text": "Моя картинка"})
        owner = game.player(tokens[0])["id"]
        job = row["image_jobs"][owner]
        game.lobby(tokens[0])
        before = copy.deepcopy(game.state)
        self.assertFalse(
            game.apply_image(row["round_id"], owner, job["id"], image="late.png")
        )
        self.assertEqual(before, game.state)

    def test_timeout_moderation_edit_window_and_snapshot_copy(self):
        game, tokens, clock = self.room("clue")
        row = game.current()
        game.generate(
            tokens[0], {"round_id": row["round_id"], "text": "Описание картинки"}
        )
        owner = game.player(tokens[0])["id"]
        job = row["image_jobs"][owner]
        game.apply_image(
            row["round_id"], owner, job["id"], error="Измени описание", moderated=True
        )
        with self.assertRaises(GameError):
            game.generate(
                tokens[0], {"round_id": row["round_id"], "text": "Описание картинки"}
            )
        snapshot = copy.deepcopy(game.state)
        restored = GameRoom(
            "ABCDEF",
            "Компания",
            snapshot,
            catalog=CATALOG_SNAPSHOT,
            clock=lambda: clock[0],
        )
        snapshot["phase"] = "broken"
        self.assertEqual(restored.state["phase"], "answer")
        clock[0] += 200
        game.progress()
        self.assertEqual(game.state["phase"], "reveal")
        self.assertTrue(all(player["score"] == 0 for player in game.state["players"]))


if __name__ == "__main__":
    unittest.main()
