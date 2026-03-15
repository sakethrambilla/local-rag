import { configureStore } from '@reduxjs/toolkit'
import { TypedUseSelectorHook, useDispatch, useSelector } from 'react-redux'
import { api } from './api'
// projectsApi is injected into the base api — import ensures endpoints are registered
import '@/store/projectsApi'
// generatedDocumentsApi is injected into the base api — import ensures endpoints are registered
import '@/store/generatedDocumentsApi'
import chatReducer from './chatSlice'
import documentsReducer from './documentsSlice'
import settingsReducer from './settingsSlice'

export const store = configureStore({
  reducer: {
    [api.reducerPath]: api.reducer,
    chat: chatReducer,
    documents: documentsReducer,
    settings: settingsReducer,
  },
  middleware: (getDefaultMiddleware) =>
    getDefaultMiddleware().concat(api.middleware),
})

export type RootState = ReturnType<typeof store.getState>
export type AppDispatch = typeof store.dispatch

export const useAppDispatch: () => AppDispatch = useDispatch
export const useAppSelector: TypedUseSelectorHook<RootState> = useSelector
