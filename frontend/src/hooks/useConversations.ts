import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { conversationsApi } from '@/services/api';

export const useConversations = () => {
  return useQuery({
    queryKey: ['conversations'],
    queryFn: () => conversationsApi.list(),
    refetchInterval: 30000,
  });
};

export const useConversation = (id: string) => {
  return useQuery({
    queryKey: ['conversation', id],
    queryFn: () => conversationsApi.get(id),
    enabled: !!id,
    refetchInterval: 10000,
  });
};

export const useCloseConversation = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => conversationsApi.close(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['conversations'] });
    },
  });
};

export const useEscalateConversation = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => conversationsApi.escalate(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['conversations'] });
    },
  });
};
