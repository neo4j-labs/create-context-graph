"use client";

import React from "react";
import { Box, Flex, Text, Button } from "@chakra-ui/react";
import { AlertTriangle } from "lucide-react";

interface Props {
  children: React.ReactNode;
  fallbackMessage?: string;
}

interface State {
  hasError: boolean;
}

export class ErrorBoundary extends React.Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error("ErrorBoundary caught:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <Flex h="100%" align="center" justify="center" direction="column" gap={3} p={4}>
          <AlertTriangle size={32} color="#E53E3E" />
          <Text fontWeight="medium" color="gray.700">
            {this.props.fallbackMessage || "Something went wrong"}
          </Text>
          <Text fontSize="sm" color="gray.500" textAlign="center">
            An error occurred while rendering this component.
          </Text>
          <Button
            size="sm"
            variant="outline"
            onClick={() => this.setState({ hasError: false })}
          >
            Try again
          </Button>
        </Flex>
      );
    }

    return this.props.children;
  }
}
