import React from "react";
import ReactDOM from "react-dom/client";
import { CommandCenterApp } from "./components/CommandCenterApp";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <CommandCenterApp />
  </React.StrictMode>,
);
