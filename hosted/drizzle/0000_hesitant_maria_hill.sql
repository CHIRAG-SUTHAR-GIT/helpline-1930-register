CREATE TABLE `entries` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`request_id` text NOT NULL,
	`calling_helpline` text DEFAULT '' NOT NULL,
	`victim_name` text NOT NULL,
	`dob` text DEFAULT '' NOT NULL,
	`pin` text DEFAULT '' NOT NULL,
	`recorded_at` text NOT NULL,
	`mo` text NOT NULL,
	`mobile` text NOT NULL,
	`notice_helpline` text DEFAULT '' NOT NULL,
	`remarks` text DEFAULT '' NOT NULL,
	`created_by` text NOT NULL,
	`remarks_version` integer DEFAULT 0 NOT NULL,
	`remarks_updated_at` text,
	`remarks_updated_by` text,
	CONSTRAINT "victim_name_length" CHECK(length("entries"."victim_name") BETWEEN 2 AND 120),
	CONSTRAINT "mo_length" CHECK(length("entries"."mo") BETWEEN 1 AND 3000),
	CONSTRAINT "remarks_length" CHECK(length("entries"."remarks") <= 5000)
);
--> statement-breakpoint
CREATE UNIQUE INDEX `entries_request_id_unique` ON `entries` (`request_id`);--> statement-breakpoint
CREATE INDEX `entries_date_idx` ON `entries` (`recorded_at`);--> statement-breakpoint
CREATE TABLE `remark_history` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`entry_id` integer NOT NULL,
	`old_remarks` text NOT NULL,
	`new_remarks` text NOT NULL,
	`changed_at` text NOT NULL,
	`changed_by` text NOT NULL,
	`version` integer NOT NULL,
	FOREIGN KEY (`entry_id`) REFERENCES `entries`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE UNIQUE INDEX `history_entry_version_idx` ON `remark_history` (`entry_id`,`version`);