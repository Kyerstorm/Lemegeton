import type { ReactNode } from "react";
import { Empty } from "../Feedback/EmptyState";

export interface DataTableColumn<Row> {
  key: string;
  label: string;
  render: (row: Row) => ReactNode;
}

export function DataTable<Row>({ columns, rows, rowKey, emptyLabel, label }: {
  columns: readonly DataTableColumn<Row>[];
  rows: readonly Row[];
  rowKey: (row: Row, index: number) => string;
  emptyLabel: string;
  label: string;
}) {
  if (!rows.length) return <Empty>{emptyLabel}</Empty>;
  return (
    <div className="table-scroll">
      <table className="ui-data-table" aria-label={label}>
        <thead><tr>{columns.map(column => <th key={column.key} scope="col">{column.label}</th>)}</tr></thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={rowKey(row, index)}>
              {columns.map(column => <td key={column.key}>{column.render(row)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
