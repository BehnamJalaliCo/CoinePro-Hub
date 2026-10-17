'use client';

import { createContext, useContext } from 'react';
import type { StreamEvent, StreamState } from './stream';

export const LiveContext = createContext<{ state: StreamState; last: StreamEvent | null; feed: StreamEvent[] }>({ state: 'connecting', last: null, feed: [] });
export const useLive = () => useContext(LiveContext);
