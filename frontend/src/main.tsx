import React from "react";
import ReactDOM from "react-dom/client";
import App from "./app/App";

import "./styles/base.css";
import "./styles/layout.css";
import "./styles/components.css";
import "./styles/panels.css";
import "./styles/views.css";

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("Unable to find root element");
}

ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
