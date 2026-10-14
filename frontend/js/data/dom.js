/** Shared DOM selection helpers for ES modules. */
export const $ = (selector, parent=document) => parent.querySelector(selector);
export const $$ = (selector, parent=document) => [...parent.querySelectorAll(selector)];
