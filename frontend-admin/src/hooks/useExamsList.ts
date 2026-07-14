import { useQuery } from "@tanstack/react-query";
import { examsApi } from "../api/exams";

/** The shared exams list query (queryKey ["exams"]). Pass enabled=false to skip
 * fetching (e.g. when a page is locked to a single section). Returns the full
 * query result so callers can read data / isLoading. */
export function useExamsList(enabled = true) {
  return useQuery({ queryKey: ["exams"], queryFn: examsApi.list, enabled });
}
