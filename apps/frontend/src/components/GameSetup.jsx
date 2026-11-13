import React, { useEffect, useState } from "react";
import { ArrowRight, Check, Minus, Plus, Users, Shuffle } from "lucide-react";

const SEATS = [2, 4, 6, 8, 12];
const defaults = { name: "Наша компания", capacity: 6, count: 3, mode: "mix" };

export default function GameSetup({
  initial = defaults,
  modes,
  busy,
  onSubmit,
  creating = false,
  players = 0,
}) {
  const [draft, setDraft] = useState(initial);
  const [custom, setCustom] = useState(
    initial.capacity !== null && !SEATS.includes(initial.capacity),
  );
  const [catalog, setCatalog] = useState(initial.mode !== "mix");
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    setDraft(initial);
    setCustom(initial.capacity !== null && !SEATS.includes(initial.capacity));
    setCatalog(initial.mode !== "mix");
  }, [initial.name, initial.capacity, initial.count, initial.mode]);
  function change(next) {
    setDraft((previous) => ({ ...previous, ...next }));
    setSaved(false);
    setError("");
  }
  async function submit(event) {
    event.preventDefault();
    if (
      draft.capacity !== null &&
      (!Number.isSafeInteger(draft.capacity) ||
        draft.capacity < 2 ||
        draft.capacity < players)
    ) {
      setError("Мест должно хватать всем участникам. Минимум — два.");
      return;
    }
    const result = await onSubmit({ ...draft, name: draft.name.trim() });
    if (result) setSaved(true);
  }
  return (
    <form className="game-setup" onSubmit={submit}>
      <label className="setup-name">
        Как назовём комнату?
        <input
          value={draft.name}
          maxLength={40}
          onChange={(event) => change({ name: event.target.value })}
          placeholder="Например, Пельменный рейв"
          required
          disabled={busy}
        />
      </label>
      <fieldset disabled={busy} className="setup-fieldset">
        <legend>
          <span className="setup-number">01</span>Сколько вас?
        </legend>
        <div
          className="seat-choices"
          role="group"
          aria-label="Количество участников"
        >
          {SEATS.map((seats) => (
            <button
              key={seats}
              type="button"
              className="seat-choice"
              aria-pressed={!custom && draft.capacity === seats}
              onClick={() => {
                setCustom(false);
                change({ capacity: seats });
              }}
            >
              <Users size={15} />
              <b>{seats}</b>
            </button>
          ))}
          <button
            type="button"
            className="seat-choice seat-infinity"
            aria-pressed={draft.capacity === null}
            onClick={() => {
              setCustom(false);
              change({ capacity: null });
            }}
          >
            <b>∞</b>
            <small>без лимита</small>
          </button>
          <button
            type="button"
            className="seat-custom"
            aria-pressed={custom}
            onClick={() => {
              setCustom(true);
              if (draft.capacity === null) change({ capacity: 6 });
            }}
          >
            Своё число
          </button>
        </div>
        {custom && (
          <label className="custom-seats">
            Количество мест
            <input
              type="number"
              min={Math.max(2, players)}
              step="1"
              value={draft.capacity ?? ""}
              onChange={(event) =>
                change({
                  capacity:
                    event.target.value === "" ? "" : Number(event.target.value),
                })
              }
              required
            />
          </label>
        )}
        <p className="setup-hint">
          {draft.capacity === null
            ? "Зайти сможет вся компания."
            : "Это лимит мест. Начать можно от двух игроков."}
        </p>
      </fieldset>
      <fieldset disabled={busy} className="setup-fieldset round-choice">
        <legend>
          <span className="setup-number">02</span>Раунды
        </legend>
        <div className="round-control">
          <button
            type="button"
            aria-label="Уменьшить число раундов"
            disabled={busy || draft.count <= 1}
            onClick={() => change({ count: draft.count - 1 })}
          >
            <Minus size={18} />
          </button>
          <output aria-label="Количество раундов">{draft.count}</output>
          <button
            type="button"
            aria-label="Увеличить число раундов"
            disabled={busy || draft.count >= 12}
            onClick={() => change({ count: draft.count + 1 })}
          >
            <Plus size={18} />
          </button>
        </div>
        <div
          className="round-shortcuts"
          role="group"
          aria-label="Быстрый выбор раундов"
        >
          {[3, 5, 8, 12].map((count) => (
            <button
              type="button"
              key={count}
              aria-pressed={draft.count === count}
              onClick={() => change({ count })}
            >
              {count}
            </button>
          ))}
        </div>
      </fieldset>
      <fieldset disabled={busy} className="setup-fieldset">
        <legend>
          <span className="setup-number">03</span>Во что играем?
        </legend>
        <div className="game-type-tabs" role="group" aria-label="Выбор режима">
          <button
            type="button"
            aria-pressed={!catalog}
            onClick={() => {
              setCatalog(false);
              change({ mode: "mix" });
            }}
          >
            <Shuffle size={17} />
            <span>
              <b>Микс бенгеров</b>
              <small>Разные игры в одной партии</small>
            </span>
          </button>
          <button
            type="button"
            aria-pressed={catalog}
            onClick={() => {
              setCatalog(true);
              if (draft.mode === "mix") change({ mode: "excuses" });
            }}
          >
            <span>
              <b>Своя игра</b>
              <small>Выбери любимый формат</small>
            </span>
            <ArrowRight size={18} />
          </button>
        </div>
        {catalog && (
          <div className="setup-games" role="group" aria-label="Миниигры">
            {Object.entries(modes).map(([id, mode]) => (
              <button
                type="button"
                key={id}
                aria-pressed={draft.mode === id}
                onClick={() => change({ mode: id })}
              >
                <span aria-hidden="true">{mode[2]}</span>
                <span>
                  <b>{mode[0]}</b>
                  <small>{mode[1]}</small>
                </span>
                {draft.mode === id && <Check size={15} />}
              </button>
            ))}
          </div>
        )}
      </fieldset>
      {error && (
        <p className="setup-validation" role="alert">
          {error}
        </p>
      )}
      <div className="setup-submit">
        <button
          type="submit"
          className="primary"
          disabled={busy || !draft.name.trim()}
        >
          {creating
            ? "Создать комнату"
            : saved
              ? "Настройки сохранены"
              : "Сохранить настройки"}
          {saved && !creating ? <Check size={19} /> : <ArrowRight size={19} />}
        </button>
        <p>
          {creating
            ? "Первый вошедший игрок станет ведущим."
            : "Настройки применятся после сохранения."}
        </p>
      </div>
    </form>
  );
}
