import { useQueryClient } from '@tanstack/react-query';

export function useApi() {
  const queryClient = useQueryClient();

  const invalidateQueries = (key: string[]) => {
    queryClient.invalidateQueries({ queryKey: key });
  };

  return {
    invalidateQueries,
  };
}
