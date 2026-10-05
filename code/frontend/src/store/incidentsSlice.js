/**
 * HW5 Part 1.III - Redux Toolkit slice for the primary domain entity.
 *
 * This file replaces the useState/useCallback data layer that lived in
 * App.jsx through HW4. Everything the app knows about incidents -- the list,
 * whether it is loading, and the last error -- now lives here instead of in a
 * component, and any component can read it with useSelector.
 *
 * The four thunks map 1:1 onto the four endpoints the assignment names:
 *   fetchIncidents  -> GET    /api/incidents
 *   createIncident  -> POST   /api/incidents
 *   updateIncident  -> PUT    /api/incidents/{id}
 *   deleteIncident  -> DELETE /api/incidents/{id}
 */

import { createAsyncThunk, createSlice } from "@reduxjs/toolkit";

import { incidentsApi } from "../api/incidentsApi";

/**
 * FastAPI puts its error text under response.data.detail -- that is where the
 * 404 / 409 / 422 messages from HW5 Part 1.II arrive. Pulling it out here, in
 * one place, means every thunk rejects with a readable string instead of a
 * serialized Axios object.
 */
function apiError(err, fallback) {
  const detail = err?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  // 422 from Pydantic is a list of {loc, msg, type} objects, not a string.
  if (Array.isArray(detail) && detail.length) {
    const first = detail[0];
    return `${first.loc?.slice(-1)[0] ?? "field"}: ${first.msg}`;
  }
  return fallback;
}

// --- thunks ----------------------------------------------------------------

export const fetchIncidents = createAsyncThunk(
  "incidents/fetch",
  async (_, { rejectWithValue }) => {
    try {
      const page = await incidentsApi.list(1, 100, "fixed");
      return page.items;
    } catch (err) {
      return rejectWithValue(apiError(err, "Failed to load incidents"));
    }
  }
);

export const createIncident = createAsyncThunk(
  "incidents/create",
  async (incident, { rejectWithValue }) => {
    try {
      return await incidentsApi.create(incident);
    } catch (err) {
      return rejectWithValue(apiError(err, "Failed to create the incident"));
    }
  }
);

export const updateIncident = createAsyncThunk(
  "incidents/update",
  async ({ id, incident }, { rejectWithValue }) => {
    try {
      return await incidentsApi.update(id, incident);
    } catch (err) {
      return rejectWithValue(apiError(err, "Failed to update the incident"));
    }
  }
);

export const deleteIncident = createAsyncThunk(
  "incidents/delete",
  async (id, { rejectWithValue }) => {
    try {
      await incidentsApi.remove(id);
      // DELETE answers 204 with no body, so the thunk returns the id itself.
      // The reducer needs it to know which row to drop from state.
      return id;
    } catch (err) {
      return rejectWithValue(apiError(err, "Failed to delete the incident"));
    }
  }
);

// --- slice -----------------------------------------------------------------

const incidentsSlice = createSlice({
  name: "incidents",
  initialState: {
    items: [],        // replaces useState([])    in App.jsx
    status: "idle",   // replaces useState(false) for loadingIncidents
    error: null,      // replaces useState(null)  for error
  },
  reducers: {
    // Plain synchronous actions. Called on logout so the next user never sees
    // the previous user's rows.
    cleared(state) {
      state.items = [];
      state.status = "idle";
      state.error = null;
    },
    errorDismissed(state) {
      state.error = null;
    },
  },
  extraReducers: (builder) => {
    builder
      // --- read ---
      .addCase(fetchIncidents.pending, (state) => {
        state.status = "loading";
        state.error = null;
      })
      .addCase(fetchIncidents.fulfilled, (state, action) => {
        state.status = "succeeded";
        state.items = action.payload;
      })
      .addCase(fetchIncidents.rejected, (state, action) => {
        state.status = "failed";
        state.error = action.payload;
      })

      // --- create ---
      // The new record is pushed straight into state. No second GET: the POST
      // response already carries the saved row, so re-fetching the whole list
      // would be a wasted round-trip.
      .addCase(createIncident.fulfilled, (state, action) => {
        state.items.push(action.payload);
        state.error = null;
      })
      .addCase(createIncident.rejected, (state, action) => {
        state.error = action.payload;
      })

      // --- update ---
      .addCase(updateIncident.fulfilled, (state, action) => {
        const i = state.items.findIndex((x) => x.id === action.payload.id);
        if (i !== -1) state.items[i] = action.payload;
        state.error = null;
      })
      .addCase(updateIncident.rejected, (state, action) => {
        state.error = action.payload;
      })

      // --- delete ---
      .addCase(deleteIncident.fulfilled, (state, action) => {
        state.items = state.items.filter((x) => x.id !== action.payload);
        state.error = null;
      })
      .addCase(deleteIncident.rejected, (state, action) => {
        state.error = action.payload;
      });
  },
});

export const { cleared, errorDismissed } = incidentsSlice.actions;

// --- selectors -------------------------------------------------------------
// Components import these instead of reaching into state shape directly, so
// renaming a field here never means editing every component.

export const selectIncidents = (state) => state.incidents.items;
export const selectIncidentsStatus = (state) => state.incidents.status;
export const selectIncidentsError = (state) => state.incidents.error;
export const selectIncidentById = (state, id) =>
  state.incidents.items.find((i) => String(i.id) === String(id));

export default incidentsSlice.reducer;