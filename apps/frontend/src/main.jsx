import React from "react";
import { createRoot } from "react-dom/client";
import Game, { isTV, roomCode, api } from "./pages/Game";
import RoomHub from "./components/RoomHub";

const root = document.getElementById("root");
if (isTV) root.classList.add("tv-root");
else document.body.classList.add("controller-page");
createRoot(root).render(
  roomCode ? <Game /> : <RoomHub request={api} isTV={isTV} />,
);
