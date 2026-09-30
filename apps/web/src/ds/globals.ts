import React from 'react';
import * as ReactDOM from 'react-dom';
import * as ReactDOMClient from 'react-dom/client';

declare global {
  interface Window {
    React: typeof React;
    ReactDOM: typeof ReactDOM & typeof ReactDOMClient;
  }
}

window.React = React;
window.ReactDOM = { ...ReactDOM, ...ReactDOMClient };
