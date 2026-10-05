/**
 * HW5 Part 1.III - session state in Redux.
 *
 * The assignment only requires a slice for the primary domain entity. This
 * second slice is here because App.jsx was also holding `user` and
 * `authChecked` in useState, and leaving them there would mean App still
 * drills props into Login while Home reads the store -- two patterns in one
 * file, which is harder to read than either one alone.
 *
 * The cookie is still the real session authority. This slice only mirrors
 * "who does the server say I am", so the UI can route accordingly.
 */

import { createAsyncThunk, createSlice } from "@reduxjs/toolkit";

import { authApi } from "../api/incidentsApi";

export const fetchMe = createAsyncThunk("auth/me", async (_, { rejectWithValue }) => {
  try {
    return await authApi.me();
  } catch {
    // A 401 here is the normal "not logged in yet" case on first load, not an
    // error worth showing the user.
    return rejectWithValue(null);
  }
});

export const login = createAsyncThunk(
  "auth/login",
  async ({ email, password }, { rejectWithValue }) => {
    try {
      return await authApi.login(email, password);
    } catch (err) {
      return rejectWithValue(
        err?.response?.data?.detail ?? "Invalid email or password"
      );
    }
  }
);

export const logout = createAsyncThunk("auth/logout", async () => {
  await authApi.logout();
});

const authSlice = createSlice({
  name: "auth",
  initialState: {
    user: null,
    checked: false,   // has the initial /me round-trip finished?
    error: null,
  },
  reducers: {},
  extraReducers: (builder) => {
    builder
      .addCase(fetchMe.fulfilled, (state, action) => {
        state.user = action.payload;
        state.checked = true;
      })
      .addCase(fetchMe.rejected, (state) => {
        state.user = null;
        state.checked = true;
      })
      .addCase(login.pending, (state) => {
        state.error = null;
      })
      .addCase(login.fulfilled, (state, action) => {
        state.user = action.payload;
        state.error = null;
      })
      .addCase(login.rejected, (state, action) => {
        state.error = action.payload;
      })
      .addCase(logout.fulfilled, (state) => {
        state.user = null;
      });
  },
});

export const selectUser = (state) => state.auth.user;
export const selectAuthChecked = (state) => state.auth.checked;
export const selectAuthError = (state) => state.auth.error;

export default authSlice.reducer;