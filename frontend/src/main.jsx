import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App.jsx";

import "../../src/static/css/base.css";
import "../../src/static/css/layout.css";
import "../../src/static/css/components.css";
import "../../src/static/css/views.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
