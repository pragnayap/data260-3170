/**
 * HW5 Part 1.III - the Redux store.
 *
 * configureStore is Redux Toolkit's replacement for createStore. It wires up
 * the Redux DevTools extension and the thunk middleware automatically, which
 * is why there is no middleware list here -- in classic Redux both had to be
 * configured by hand.
 *
 * The `reducer` map is what defines the shape of global state:
 *     state.incidents -> { items, status, error }
 *     state.auth      -> { user, checked, error }
 * Those are the paths every useSelector in the app reads from.
 */

import { configureStore } from "@reduxjs/toolkit";

import authReducer from "./authSlice";
import incidentsReducer from "./incidentsSlice";

export const store = configureStore({
  reducer: {
    incidents: incidentsReducer,
    auth: authReducer,
  },
});

export default store;