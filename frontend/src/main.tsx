import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";

import "./legacy/css/base.css";
import "./legacy/css/layout.css";
import "./legacy/css/components.css";
import "./legacy/css/views.css";

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("Unable to find root element");
}

ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
