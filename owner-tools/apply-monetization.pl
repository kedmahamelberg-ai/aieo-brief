#!/usr/bin/perl
use strict; use warnings; use JSON::PP; use File::Basename qw(dirname); use File::Temp qw(tempfile tempdir); use File::Copy qw(copy);
my ($path,$settings)=@ARGV; die "Use apply-monetization.pl CONFIG SETTINGS\n" unless @ARGV==2;
my $json=JSON::PP->new->utf8->canonical->pretty;
sub read_json { my($p)=@_; die "Not a regular settings file: $p\n" unless -f $p && !-l $p && -s $p < 200000; open my $f,'<:raw',$p or die $!; local $/; my $d=$json->decode(<$f>); die "Expected a settings object\n" unless ref($d) eq 'HASH'; return $d; }
my $current=read_json($path); my $patch=read_json($settings);
die "Choose Brief-Monetization.json\n" unless ($patch->{schema_version}//'') eq 'aieo_brief_monetization_v1';
for(keys %$patch){die "Unexpected settings field $_\n" unless /^(schema_version|adsense|support_url)$/;}
if(exists $patch->{adsense}){
 my $a=$patch->{adsense};die "Invalid advertising settings\n" unless ref($a) eq 'HASH';
 for(keys %$a){die "Unexpected advertising setting\n" unless /^(enabled|cmp_enabled|publisher_id|mode|slots)$/;}
 for('enabled','cmp_enabled'){die "Expected true or false\n" unless JSON::PP::is_bool($a->{$_});}
 die "Invalid publisher ID\n" unless ($a->{publisher_id}//'') =~ /^ca-pub-\d{16}$/;
 die "Invalid ad mode\n" unless ($a->{mode}//'') =~ /^(auto|placements)$/;
 die "Invalid ad slots\n" unless ref($a->{slots}) eq 'HASH'; my $filled=0;
 for(keys %{$a->{slots}}){die "Invalid placement\n" unless /^(feed|rail|story)$/;my $v=$a->{slots}{$_};die "Ad-unit IDs must contain only digits\n" if ref($v)||!defined($v)||$v !~ /^(\d{1,20})?$/;$filled++ if length $v;}
 die "Publish the Google consent message before enabling ads\n" if $a->{enabled} && !$a->{cmp_enabled};
 die "Add an ad-unit ID\n" if $a->{enabled} && $a->{mode} eq 'placements' && !$filled;
 $current->{adsense}={%{$current->{adsense}//{}},%$a};
 $current->{site_url}='https://brief.hamelberg-ai.com' unless $current->{site_url};
}
if(exists $patch->{support_url}){my $u=$patch->{support_url};die "Use a complete HTTPS support link\n" if ref($u)||!defined($u)||($u ne '' && $u !~ m{^https://[A-Za-z0-9.-]+(?::\d+)?(?:[/?\#][^\s<>]*)?$});$current->{support_url}=$u;}
my $old=read_json($path);if($json->encode($old) eq $json->encode($current)){print "Settings already up to date.\n";exit 0;}
my $parent=dirname(dirname(dirname($path)));my $backup=tempdir('Brief-settings-backup-XXXXXX',DIR=>$parent,CLEANUP=>0);copy($path,"$backup/site.json") or die $!;
my($f,$temp)=tempfile('.brief-settings-XXXXXX',DIR=>dirname($path),UNLINK=>0);binmode $f;print $f $json->encode($current);close $f or die $!;chmod 0644,$temp;rename $temp,$path or die $!;
print "Monetization settings saved. Backup: $backup\nCommit and push aieo-brief in GitHub Desktop.\n";
