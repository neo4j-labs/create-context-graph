"use client";

import { useState, useEffect } from "react";
import {
  Box,
  Heading,
  Text,
  VStack,
  HStack,
  Badge,
  Button,
  Flex,
} from "@chakra-ui/react";
import { FileText, ArrowLeft, ChevronLeft, ChevronRight } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { API_BASE } from "@/lib/config";

const PAGE_SIZE = 20;

interface DocumentSummary {
  title: string;
  template_id: string;
  template_name: string;
  preview: string;
  mentioned_entities: { name: string; labels: string[] }[];
}

interface DocumentDetail {
  document: {
    title: string;
    content: string;
    template_id: string;
    template_name: string;
  };
  mentioned_entities: { name: string; labels: string[] }[];
}

export function DocumentBrowser() {
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [selectedDoc, setSelectedDoc] = useState<DocumentDetail | null>(null);
  const [filterTemplate, setFilterTemplate] = useState<string>("");
  const [page, setPage] = useState(0);
  const [hasMore, setHasMore] = useState(false);

  useEffect(() => {
    setPage(0);
  }, [filterTemplate]);

  useEffect(() => {
    loadDocuments();
  }, [filterTemplate, page]);

  async function loadDocuments() {
    try {
      const params = new URLSearchParams();
      if (filterTemplate) params.set("template_id", filterTemplate);
      params.set("skip", String(page * PAGE_SIZE));
      params.set("limit", String(PAGE_SIZE + 1)); // fetch one extra to detect more
      const res = await fetch(`${API_BASE}/documents?${params}`, { signal: AbortSignal.timeout(10000) });
      const data = await res.json();
      const docs = data.documents || [];
      setHasMore(docs.length > PAGE_SIZE);
      setDocuments(docs.slice(0, PAGE_SIZE));
    } catch {
      // Backend may not be running yet
    }
  }

  async function selectDocument(title: string) {
    try {
      const res = await fetch(
        `${API_BASE}/documents/${encodeURIComponent(title)}`,
        { signal: AbortSignal.timeout(10000) }
      );
      const data = await res.json();
      setSelectedDoc(data);
    } catch {
      // ignore
    }
  }

  // Get unique template names for filter
  const templateTypes = [
    ...new Map(
      documents.map((d) => [d.template_id, d.template_name])
    ).entries(),
  ];

  return (
    <Flex direction="column" h="100%">
      <Box px={4} py={3} borderBottom="1px solid" borderColor="gray.200">
        <Heading size="sm">
          <HStack>
            <FileText size={16} />
            <span>Documents</span>
          </HStack>
        </Heading>
        <Text fontSize="xs" color="gray.500">
          {documents.length} domain documents
        </Text>
      </Box>

      {/* Template filter badges */}
      {!selectedDoc && (
        <Flex
          px={4}
          py={2}
          gap={1}
          flexWrap="wrap"
          borderBottom="1px solid"
          borderColor="gray.100"
        >
          <Badge
            cursor="pointer"
            variant={!filterTemplate ? "solid" : "outline"}
            onClick={() => setFilterTemplate("")}
            size="sm"
          >
            All
          </Badge>
          {templateTypes.map(([id, name]) => (
            <Badge
              key={id}
              cursor="pointer"
              size="sm"
              variant={filterTemplate === id ? "solid" : "outline"}
              onClick={() => setFilterTemplate(id)}
            >
              {name}
            </Badge>
          ))}
        </Flex>
      )}

      {selectedDoc ? (
        /* Full document view */
        <Box flex={1} overflow="auto" px={4} py={3}>
          <HStack
            cursor="pointer"
            onClick={() => setSelectedDoc(null)}
            mb={3}
            color="blue.500"
            fontSize="xs"
          >
            <ArrowLeft size={12} />
            <Text>Back to list</Text>
          </HStack>
          <Heading size="sm" mb={2}>
            {selectedDoc.document.title}
          </Heading>
          <Badge mb={3} size="sm">
            {selectedDoc.document.template_name}
          </Badge>
          {selectedDoc.mentioned_entities.length > 0 && (
            <HStack mb={3} flexWrap="wrap" gap={1}>
              {selectedDoc.mentioned_entities.map((e, i) => (
                <Badge key={`${e.name}-${i}`} size="sm" variant="outline">
                  {e.name}
                </Badge>
              ))}
            </HStack>
          )}
          <Box
            fontSize="sm"
            lineHeight="tall"
            color="gray.700"
            className="markdown-content"
          >
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {selectedDoc.document.content}
            </ReactMarkdown>
          </Box>
        </Box>
      ) : (
        /* Document list */
        <VStack
          flex={1}
          overflow="auto"
          px={4}
          py={2}
          gap={2}
          align="stretch"
        >
          {documents.length === 0 ? (
            <Box py={8} px={4}>
              <Flex justify="center" mb={3}>
                <FileText size={32} color="#A0AEC0" />
              </Flex>
              <Text fontSize="sm" color="gray.500" textAlign="center">
                No documents loaded
              </Text>
              <Text fontSize="xs" color="gray.400" textAlign="center" mt={2} lineHeight="tall">
                Documents are domain-specific knowledge artifacts (reports, notes, assessments)
                that the AI agent can reference when answering questions.
              </Text>
              <Box mt={3} textAlign="center">
                <Badge variant="outline" fontSize="xs" fontFamily="mono" px={2}>
                  make seed
                </Badge>
              </Box>
            </Box>
          ) : (
            documents.map((doc) => (
              <Box
                key={doc.title}
                p={3}
                borderRadius="md"
                border="1px solid"
                borderColor="gray.200"
                cursor="pointer"
                onClick={() => selectDocument(doc.title)}
                _hover={{ borderColor: "blue.200" }}
                role="button"
                tabIndex={0}
                onKeyDown={(e: React.KeyboardEvent) => {
                  if (e.key === "Enter") selectDocument(doc.title);
                }}
              >
                <Text fontSize="sm" fontWeight="medium" lineClamp={1}>
                  {doc.title}
                </Text>
                <Badge size="sm" mt={1}>
                  {doc.template_name}
                </Badge>
                <Text fontSize="xs" color="gray.500" mt={1} lineClamp={2}>
                  {doc.preview}
                </Text>
              </Box>
            ))
          )}
          {/* Pagination */}
          {(page > 0 || hasMore) && (
            <HStack justify="center" py={2} gap={2}>
              <Button
                size="xs"
                variant="outline"
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={page === 0}
                aria-label="Previous page"
              >
                <ChevronLeft size={14} /> Prev
              </Button>
              <Text fontSize="xs" color="gray.500">
                Page {page + 1}
              </Text>
              <Button
                size="xs"
                variant="outline"
                onClick={() => setPage((p) => p + 1)}
                disabled={!hasMore}
                aria-label="Next page"
              >
                Next <ChevronRight size={14} />
              </Button>
            </HStack>
          )}
        </VStack>
      )}
    </Flex>
  );
}
