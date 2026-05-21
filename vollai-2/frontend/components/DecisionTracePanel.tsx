"use client";

import { useState, useEffect } from "react";
import { Box, Heading, Text, VStack, HStack, Badge, Flex } from "@chakra-ui/react";
import { GitBranch, Brain, Wrench, Eye } from "lucide-react";
import { API_BASE } from "@/lib/config";

interface TraceStep {
  step_number: number;
  thought: string;
  action: string;
  observation?: string;
}

interface DecisionTrace {
  id: string;
  task: string;
  steps: TraceStep[];
  outcome: string;
}

export function DecisionTracePanel() {
  const [traces, setTraces] = useState<DecisionTrace[]>([]);
  const [selectedTrace, setSelectedTrace] = useState<DecisionTrace | null>(null);

  useEffect(() => {
    loadTraces();
  }, []);

  async function loadTraces() {
    try {
      const res = await fetch(`${API_BASE}/traces`, { signal: AbortSignal.timeout(10000) });
      const data = await res.json();
      if (data.traces) {
        setTraces(
          data.traces.map((t: Record<string, unknown>) => ({
            id: (t.id as string) || "",
            task: (t.task as string) || "",
            steps: ((t.steps as TraceStep[]) || []).filter(
              (s) => s && s.thought
            ),
            outcome: (t.outcome as string) || "",
          }))
        );
      }
    } catch {
      // Backend may not be running yet
    }
  }

  return (
    <Flex direction="column" h="100%">
      <Box px={4} py={3} borderBottom="1px solid" borderColor="gray.200">
        <Heading size="sm">
          <HStack>
            <GitBranch size={16} />
            <span>Decision Traces</span>
          </HStack>
        </Heading>
        <Text fontSize="xs" color="gray.500">
          Reasoning provenance & causal chains
        </Text>
      </Box>

      <VStack flex={1} overflow="auto" px={4} py={2} gap={2} align="stretch">
        {traces.length === 0 ? (
          <Box py={8} px={4}>
            <Flex justify="center" mb={3}>
              <GitBranch size={32} color="#A0AEC0" />
            </Flex>
            <Text fontSize="sm" color="gray.500" textAlign="center">
              No decision traces yet
            </Text>
            <Text fontSize="xs" color="gray.400" textAlign="center" mt={2} lineHeight="tall">
              Decision traces capture multi-step reasoning chains — the thoughts,
              actions, and observations an agent uses to reach a conclusion.
            </Text>
            <Box mt={3} textAlign="center">
              <Badge variant="outline" fontSize="xs" fontFamily="mono" px={2}>
                make seed
              </Badge>
            </Box>
          </Box>
        ) : (
          traces.map((trace) => (
            <Box
              key={trace.id}
              p={3}
              borderRadius="md"
              border="1px solid"
              borderColor={
                selectedTrace?.id === trace.id ? "blue.300" : "gray.200"
              }
              cursor="pointer"
              onClick={() => setSelectedTrace(trace)}
              _hover={{ borderColor: "blue.200" }}
            >
              <Text fontSize="sm" fontWeight="medium" lineClamp={2}>
                {trace.task}
              </Text>
              <HStack mt={1}>
                <Badge size="sm" variant="outline">
                  <Brain size={10} />
                  {trace.steps.length} steps
                </Badge>
                {trace.outcome && (
                  <Badge size="sm" colorPalette="green">
                    Resolved
                  </Badge>
                )}
              </HStack>
            </Box>
          ))
        )}
      </VStack>

      {/* Selected trace detail */}
      {selectedTrace && (
        <Box
          borderTop="1px solid"
          borderColor="gray.200"
          px={4}
          py={3}
          maxH="50%"
          overflow="auto"
        >
          <Text fontSize="sm" fontWeight="bold" mb={2}>
            {selectedTrace.task}
          </Text>
          <VStack gap={3} align="stretch">
            {selectedTrace.steps.map((step, i) => (
              <Box key={i} pl={3} borderLeft="2px solid" borderColor="blue.200">
                <HStack>
                  <Brain size={12} />
                  <Text fontSize="xs" color="gray.600">
                    {step.thought}
                  </Text>
                </HStack>
                <HStack mt={1}>
                  <Wrench size={12} />
                  <Text fontSize="xs" fontFamily="mono">
                    {step.action}
                  </Text>
                </HStack>
                {step.observation && (
                  <HStack mt={1}>
                    <Eye size={12} />
                    <Text fontSize="xs" color="green.700">
                      {step.observation}
                    </Text>
                  </HStack>
                )}
              </Box>
            ))}
          </VStack>
          {selectedTrace.outcome && (
            <Box mt={3} p={2} bg="green.50" borderRadius="md">
              <Text fontSize="xs" fontWeight="bold">
                Outcome:
              </Text>
              <Text fontSize="xs">{selectedTrace.outcome}</Text>
            </Box>
          )}
        </Box>
      )}
    </Flex>
  );
}
