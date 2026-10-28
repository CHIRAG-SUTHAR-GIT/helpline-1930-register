CREATE TABLE `helpline_history` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`entry_id` integer NOT NULL,
	`old_calling_helpline` text NOT NULL,
	`new_calling_helpline` text NOT NULL,
	`old_notice_helpline` text NOT NULL,
	`new_notice_helpline` text NOT NULL,
	`changed_at` text NOT NULL,
	`changed_by` text NOT NULL,
	`version` integer NOT NULL,
	FOREIGN KEY (`entry_id`) REFERENCES `entries`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE UNIQUE INDEX `helpline_history_entry_version_idx` ON `helpline_history` (`entry_id`,`version`);--> statement-breakpoint
ALTER TABLE `entries` ADD `helpline_version` integer DEFAULT 0 NOT NULL;--> statement-breakpoint
ALTER TABLE `entries` ADD `helpline_updated_at` text;--> statement-breakpoint
ALTER TABLE `entries` ADD `helpline_updated_by` text;