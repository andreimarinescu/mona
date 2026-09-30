import { createContext, useContext } from 'react';
import { defaultProviders, type DataProviders } from './providers';

export const DataProvidersContext = createContext<DataProviders>(defaultProviders);

export function useProviders(): DataProviders {
  return useContext(DataProvidersContext);
}
