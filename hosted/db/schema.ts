import { sql } from 'drizzle-orm';
import { sqliteTable, integer, text, index, uniqueIndex, check } from 'drizzle-orm/sqlite-core';

export const entries = sqliteTable('entries', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  request_id: text('request_id').notNull().unique(),
  calling_helpline: text('calling_helpline').notNull().default(''),
  victim_name: text('victim_name').notNull(),
  dob: text('dob').notNull().default(''),
  pin: text('pin').notNull().default(''),
  recorded_at: text('recorded_at').notNull(),
  mo: text('mo').notNull(),
  mobile: text('mobile').notNull(),
  notice_helpline: text('notice_helpline').notNull().default(''),
  remarks: text('remarks').notNull().default(''),
  created_by: text('created_by').notNull(),
  remarks_version: integer('remarks_version').notNull().default(0),
  remarks_updated_at: text('remarks_updated_at'),
  remarks_updated_by: text('remarks_updated_by'),
  helpline_version: integer('helpline_version').notNull().default(0),
  helpline_updated_at: text('helpline_updated_at'),
  helpline_updated_by: text('helpline_updated_by'),
}, table => [
  index('entries_date_idx').on(table.recorded_at),
  check('victim_name_length', sql`length(${table.victim_name}) BETWEEN 2 AND 120`),
  check('mo_length', sql`length(${table.mo}) BETWEEN 1 AND 3000`),
  check('remarks_length', sql`length(${table.remarks}) <= 5000`),
]);

export const remarkHistory = sqliteTable('remark_history', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  entry_id: integer('entry_id').notNull().references(() => entries.id),
  old_remarks: text('old_remarks').notNull(),
  new_remarks: text('new_remarks').notNull(),
  changed_at: text('changed_at').notNull(),
  changed_by: text('changed_by').notNull(),
  version: integer('version').notNull(),
}, table => [uniqueIndex('history_entry_version_idx').on(table.entry_id, table.version)]);

export const helplineHistory = sqliteTable('helpline_history', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  entry_id: integer('entry_id').notNull().references(() => entries.id),
  old_calling_helpline: text('old_calling_helpline').notNull(),
  new_calling_helpline: text('new_calling_helpline').notNull(),
  old_notice_helpline: text('old_notice_helpline').notNull(),
  new_notice_helpline: text('new_notice_helpline').notNull(),
  changed_at: text('changed_at').notNull(),
  changed_by: text('changed_by').notNull(),
  version: integer('version').notNull(),
}, table => [uniqueIndex('helpline_history_entry_version_idx').on(table.entry_id, table.version)]);
